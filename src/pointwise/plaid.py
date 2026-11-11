"""Plaid client: linking a card issuer and reading its transactions.

This exists because of a hard limit established elsewhere in this codebase: the
payment side cannot tell us which card was used. A merchant's PayPal order
names its own funding source, the buyer's Transaction Search has no card field,
and no OAuth scope reaches another account's wallet. So Pointwise can only ever
audit the purchases it routed itself -- which is a demo, not a product.

Plaid looks at the other end. It reads the card's own statement, so every
transaction arrives already tagged with the account it landed on. How the
purchase was made stops mattering: tap, Apple Pay, PayPal at a merchant, card
number typed into a form -- it all posts to the card, and the card is what we
read.

Sandbox only here. Nothing in this module should be pointed at a real bank
without a serious look at what the stored access token is and what losing it
would mean.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}

#: Plaid's canned test institution. Its sandbox items come with credit card
#: accounts and a month of transactions already attached, which is exactly the
#: shape this app needs and saves putting a Link UI in front of a demo.
SANDBOX_INSTITUTION = "ins_109508"

#: Only Transactions is requested. Asking for auth or identity would widen the
#: consent screen for data this app has no use for.
PRODUCTS = ["transactions"]


class PlaidNotConfigured(RuntimeError):
    """Raised when a call needs credentials that were never supplied."""


class PlaidConfig(BaseModel):
    """Credentials, read from the environment. Never hard-code these."""

    model_config = ConfigDict(frozen=True)

    client_id: str | None = None
    secret: str | None = None
    environment: str = "sandbox"

    @classmethod
    def from_env(cls) -> PlaidConfig:
        return cls(
            client_id=os.environ.get("PLAID_CLIENT_ID") or None,
            secret=os.environ.get("PLAID_SECRET") or None,
            environment=os.environ.get("PLAID_ENV", "sandbox"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.secret)

    @property
    def base_url(self) -> str:
        return HOSTS.get(self.environment, HOSTS["sandbox"])

    @property
    def is_sandbox(self) -> bool:
        return self.environment == "sandbox"


class PlaidAccount(BaseModel):
    """One account behind a linked item, as Plaid describes it."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    name: str
    mask: str | None = None
    type: str
    subtype: str | None = None

    @property
    def is_credit_card(self) -> bool:
        """Only credit cards can win a recommendation.

        A linked login usually carries chequing and savings too, and offering
        to map those onto a rewards card would be nonsense.
        """
        return self.type == "credit" or self.subtype == "credit card"

    @property
    def label(self) -> str:
        return f"{self.name} ••{self.mask}" if self.mask else self.name


class PlaidTransaction(BaseModel):
    """One posted or pending transaction."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    account_id: str
    amount: Decimal
    on: date
    name: str
    merchant_name: str | None = None
    #: Plaid's own classification, e.g. FOOD_AND_DRINK. Useful as a category
    #: signal that is better than reading words out of a merchant's name.
    category_primary: str | None = None
    #: The one that is actually usable. The primary lumps groceries in with
    #: restaurants, which are different card categories.
    category_detailed: str | None = None
    pending: bool = False

    @property
    def best_name(self) -> str:
        """The cleanest merchant string available.

        A raw card feed is ugly -- "SQ *TARTINE BAKERY SF 0423" -- and Plaid's
        enriched merchant_name is far more likely to resolve to a category.
        """
        return self.merchant_name or self.name


class PlaidClient:
    """Thin wrapper over the handful of Plaid endpoints this app needs.

    Raw httpx rather than the official SDK, matching `paypal.py`: four
    endpoints, one auth shape, and one less dependency to pin.
    """

    def __init__(self, config: PlaidConfig | None = None):
        self.config = config or PlaidConfig.from_env()

    @property
    def configured(self) -> bool:
        return self.config.configured

    def _post(self, path: str, payload: dict[str, Any]) -> dict:
        if not self.config.configured:
            raise PlaidNotConfigured(
                "Set PLAID_CLIENT_ID and PLAID_SECRET in .env to link a card issuer."
            )
        response = httpx.post(
            f"{self.config.base_url}{path}",
            json={
                "client_id": self.config.client_id,
                "secret": self.config.secret,
                **payload,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()

    # ----------------------------------------------------------- linking

    def create_link_token(self, user_id: str = "pointwise-demo-user") -> dict:
        """A token for Plaid Link, hosted so no native SDK is needed.

        The app runs in Expo Go, which cannot load Plaid's native Link SDK, so
        this asks for a hosted URL to open in a web view instead.
        """
        return self._post(
            "/link/token/create",
            {
                "user": {"client_user_id": user_id},
                "client_name": "Pointwise",
                "products": PRODUCTS,
                "country_codes": ["US"],
                "language": "en",
                "hosted_link": {},
            },
        )

    def create_sandbox_item(
        self, institution_id: str = SANDBOX_INSTITUTION
    ) -> str:
        """Mint a linked sandbox item directly, skipping the Link UI.

        Sandbox only, and the reason it exists: it exercises every downstream
        path -- exchange, accounts, transactions -- without a web view, a login
        form or a human. The demo gets a connected issuer in one tap.
        """
        if not self.config.is_sandbox:
            raise PlaidNotConfigured(
                "Sandbox items can only be created in the sandbox environment."
            )
        body = self._post(
            "/sandbox/public_token/create",
            {"institution_id": institution_id, "initial_products": PRODUCTS},
        )
        return body["public_token"]

    def exchange(self, public_token: str) -> dict:
        """Swap a public token for the long-lived access token."""
        return self._post(
            "/item/public_token/exchange", {"public_token": public_token}
        )

    # ------------------------------------------------------------ reading

    def accounts(self, access_token: str) -> list[PlaidAccount]:
        body = self._post("/accounts/get", {"access_token": access_token})
        return [
            PlaidAccount(
                account_id=a["account_id"],
                name=a.get("name") or "Account",
                mask=a.get("mask"),
                type=a.get("type") or "",
                subtype=a.get("subtype"),
            )
            for a in body.get("accounts", [])
        ]

    def sync(self, access_token: str, cursor: str | None = None) -> dict:
        """One page of the incremental transaction feed.

        Returns the raw envelope rather than just the rows, because the caller
        has to persist `next_cursor` -- losing it means re-reading the whole
        history and duplicating every row.
        """
        payload: dict[str, Any] = {"access_token": access_token, "count": 500}
        if cursor:
            payload["cursor"] = cursor
        body = self._post("/transactions/sync", payload)
        return {
            "added": [self._row(t) for t in body.get("added", [])],
            "modified": [self._row(t) for t in body.get("modified", [])],
            "removed": [t["transaction_id"] for t in body.get("removed", [])],
            "next_cursor": body.get("next_cursor"),
            "has_more": bool(body.get("has_more")),
        }

    @staticmethod
    def _row(t: dict) -> PlaidTransaction:
        category = t.get("personal_finance_category") or {}
        return PlaidTransaction(
            transaction_id=t["transaction_id"],
            account_id=t["account_id"],
            # Plaid reports a card purchase as a positive amount. Decimal via
            # str, because a float here would quietly lose cents.
            amount=Decimal(str(t.get("amount", 0))),
            on=date.fromisoformat(t["date"]),
            name=t.get("name") or "",
            merchant_name=t.get("merchant_name"),
            category_primary=category.get("primary"),
            category_detailed=category.get("detailed"),
            pending=bool(t.get("pending")),
        )
