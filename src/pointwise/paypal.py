"""PayPal REST client: OAuth, Vault, Orders and Transaction Search.

Sandbox by default. The client degrades rather than crashes when credentials
are absent, because the app has to render before anyone has pasted a secret in
-- the UI says "not connected" instead of throwing.

Nothing here computes a reward. PayPal supplies transactions and moves money;
the engine decides which card should have been used.
"""

from __future__ import annotations

import base64
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

#: Load .env once, at import. Without this nothing reads the file and a pasted
#: credential looks absent, which is a confusing way to fail.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

SANDBOX = "https://api-m.sandbox.paypal.com"
LIVE = "https://api-m.paypal.com"


class PayPalNotConfigured(RuntimeError):
    """Raised when a call needs credentials that were never supplied."""


class PayPalConfig(BaseModel):
    """Credentials, read from the environment.

    Never hard-code these and never commit them. `.env` is gitignored; see
    `.env.example` for the shape.
    """

    model_config = ConfigDict(frozen=True)

    client_id: str | None = None
    client_secret: str | None = None
    environment: str = "sandbox"

    @classmethod
    def from_env(cls) -> PayPalConfig:
        return cls(
            client_id=os.environ.get("PAYPAL_CLIENT_ID") or None,
            client_secret=os.environ.get("PAYPAL_CLIENT_SECRET") or None,
            environment=os.environ.get("PAYPAL_ENV", "sandbox"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def base_url(self) -> str:
        return LIVE if self.environment == "live" else SANDBOX


class PayPalTransaction(BaseModel):
    """One posted transaction, flattened out of PayPal's reporting shape."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    merchant_name: str
    amount: Decimal
    currency: str
    on: date
    #: PayPal's reporting payload has no documented MCC field, so the category
    #: still has to be inferred from the merchant name downstream.
    raw_event_code: str | None = None


class PayPalClient:
    """Thin, synchronous client. One access token, cached until it expires."""

    def __init__(self, config: PayPalConfig | None = None, timeout_s: float = 20.0):
        self.config = config or PayPalConfig.from_env()
        self._timeout = timeout_s
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._scopes: frozenset[str] = frozenset()

    @property
    def configured(self) -> bool:
        return self.config.configured

    def _require(self) -> None:
        if not self.configured:
            raise PayPalNotConfigured(
                "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET. Create a REST "
                "app at developer.paypal.com and copy them into .env."
            )

    def access_token(self) -> str:
        """Fetch or reuse an OAuth token."""
        self._require()
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token

        secret = f"{self.config.client_id}:{self.config.client_secret}".encode()
        response = httpx.post(
            f"{self.config.base_url}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {base64.b64encode(secret).decode()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content="grant_type=client_credentials",
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        # PayPal returns exactly what this app is allowed to do. Reading it is
        # how the UI can say "vault not enabled" instead of discovering it as
        # a 403 in the middle of someone's checkout.
        self._scopes = frozenset(payload.get("scope", "").split())
        # Expire a minute early so a token never dies mid-request.
        self._token_expires_at = now + timedelta(
            seconds=max(60, int(payload.get("expires_in", 32400)) - 60)
        )
        return self._token

    def _request(
        self, method: str, path: str, request_id: str | None = None, **kwargs: Any
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "Content-Type": "application/json",
        }
        if request_id:
            # PayPal's idempotency key. Required whenever a payment_source is
            # present, and the only thing stopping a retried order from
            # charging the customer twice.
            headers["PayPal-Request-Id"] = request_id

        response = httpx.request(
            method,
            f"{self.config.base_url}{path}",
            headers=headers,
            timeout=self._timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    # ----------------------------------------------------------- capabilities

    #: The Vault v3 scope. Granted by the "Save payment methods" capability on
    #: the REST app, which in turn needs the account approved for Expanded
    #: Checkout. Without it, setup tokens return NOT_AUTHORIZED.
    VAULT_V3_SCOPE = "https://uri.paypal.com/services/vault/payment-tokens/readwrite"
    VAULT_V1_SCOPE = "https://api.paypal.com/v1/vault/credit-card"

    def granted_scopes(self) -> frozenset[str]:
        """What this app is authorized for, straight from the token response."""
        self.access_token()
        return self._scopes

    @property
    def vault_v3_enabled(self) -> bool:
        """Whether vaulted cards can fund an Orders v2 capture."""
        return self.VAULT_V3_SCOPE in self.granted_scopes()

    @property
    def vault_v1_enabled(self) -> bool:
        """Whether cards can be stored at all, even if not chargeable."""
        return self.VAULT_V1_SCOPE in self.granted_scopes()

    # ------------------------------------------------------------------ vault

    def vault_card(self, card: dict, customer_id: str | None = None) -> dict:
        """Store a card and return its Vault v3 payment token.

        Both halves of PayPal's two-step dance in one call, because a setup
        token is useless on its own and expires in minutes. The returned id is
        what `create_order` accepts as `vault_id`.
        """
        setup = self.create_setup_token(card, customer_id=customer_id)
        setup_id = setup.get("id")
        if not setup_id:
            raise RuntimeError(f"setup token had no id: {setup}")
        return self.create_payment_token(setup_id)

    def vault_card_v1(self, card: dict) -> dict:
        """Store a card in the legacy v1 vault.

        Kept because v1 is authorized on REST apps that v3 is not, and it still
        mints a real, retrievable vault id per card. It cannot fund an Orders
        v2 capture -- that is what makes it a fallback and not an alternative.
        """
        return self._request(
            "POST",
            "/v1/vault/credit-cards",
            json=card,
            request_id=f"pw-v1card-{uuid.uuid4()}",
        )

    def get_vaulted_card_v1(self, vault_id: str) -> dict:
        """Read back a v1 vault record, to prove the id is real."""
        return self._request("GET", f"/v1/vault/credit-cards/{vault_id}")

    def create_setup_token(self, card: dict, customer_id: str | None = None) -> dict:
        """Step one of saving a card: a short-lived setup token."""
        body: dict[str, Any] = {"payment_source": {"card": card}}
        if customer_id:
            body["customer"] = {"id": customer_id}
        return self._request(
            "POST",
            "/v3/vault/setup-tokens",
            json=body,
            request_id=f"pw-setup-{uuid.uuid4()}",
        )

    def create_payment_token(self, setup_token_id: str) -> dict:
        """Step two: exchange the setup token for a durable payment token."""
        return self._request(
            "POST",
            "/v3/vault/payment-tokens",
            json={"payment_source": {"token": {"id": setup_token_id, "type": "SETUP_TOKEN"}}},
            request_id=f"pw-token-{uuid.uuid4()}",
        )

    def list_payment_tokens(self, customer_id: str) -> dict:
        return self._request(
            "GET", f"/v3/vault/payment-tokens?customer_id={customer_id}"
        )

    # ----------------------------------------------------------------- orders

    def create_order(
        self,
        amount: Decimal,
        currency: str = "USD",
        vault_id: str | None = None,
        card: dict | None = None,
        description: str | None = None,
        request_id: str | None = None,
        payment_source: dict | None = None,
    ) -> dict:
        """Create an order, charging a specific funding source.

        `vault_id` is how the engine's choice becomes the funding source: the
        recommendation stops being advice at this line. `card` is the direct
        alternative for sandbox work before the Vault feature is enabled, and
        takes PayPal's published test card numbers. `payment_source` is the
        pre-assembled form and wins over both.
        """
        unit: dict[str, Any] = {
            "amount": {"currency_code": currency, "value": f"{amount:.2f}"}
        }
        if description:
            unit["description"] = description[:127]

        body: dict[str, Any] = {"intent": "CAPTURE", "purchase_units": [unit]}
        if payment_source:
            # Already-assembled source, which is what the funding registry
            # hands over. Takes precedence over the convenience arguments.
            body["payment_source"] = payment_source
        elif vault_id:
            body["payment_source"] = {"card": {"vault_id": vault_id}}
        elif card:
            body["payment_source"] = {"card": card}

        # An order carrying a payment_source must be idempotent. Callers that
        # retry should pass the same key; a fresh one is generated otherwise.
        key = request_id or f"pw-{uuid.uuid4()}"
        return self._request("POST", "/v2/checkout/orders", json=body, request_id=key)

    def capture_order(self, order_id: str) -> dict:
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture", json={})

    # ------------------------------------------------------- transaction search

    def list_transactions(self, start: date, end: date) -> list[PayPalTransaction]:
        """Posted transactions in a window.

        PayPal caps each request at 31 days and keeps roughly three years of
        history. The response has no documented merchant category code, so the
        caller must still infer the category from the merchant name.
        """
        if (end - start).days > 31:
            raise ValueError("Transaction Search accepts at most 31 days per request")

        payload = self._request(
            "GET",
            "/v1/reporting/transactions"
            f"?start_date={start.isoformat()}T00:00:00-0000"
            f"&end_date={end.isoformat()}T23:59:59-0000"
            "&fields=all&page_size=100",
        )
        return [
            parsed
            for entry in payload.get("transaction_details", [])
            if (parsed := _parse_transaction(entry)) is not None
        ]


def _parse_transaction(entry: dict) -> PayPalTransaction | None:
    """Flatten one reporting entry, skipping anything unusable.

    Only outgoing purchases matter here; credits and transfers are not spend
    and would pollute the audit with phantom missed opportunities.
    """
    info = entry.get("transaction_info") or {}
    payer = entry.get("payer_info") or {}
    raw_amount = (info.get("transaction_amount") or {}).get("value")
    if raw_amount is None:
        return None

    amount = Decimal(str(raw_amount))
    if amount >= 0:
        return None  # a credit, not a purchase

    name = (
        (payer.get("payer_name") or {}).get("alternate_full_name")
        or info.get("transaction_subject")
        or info.get("transaction_note")
        or "Unknown merchant"
    )
    initiation = info.get("transaction_initiation_date") or ""
    try:
        on = datetime.fromisoformat(initiation.replace("Z", "+00:00")).date()
    except ValueError:
        return None

    return PayPalTransaction(
        transaction_id=info.get("transaction_id", ""),
        merchant_name=str(name).strip(),
        amount=abs(amount),
        currency=(info.get("transaction_amount") or {}).get("currency_code", "USD"),
        on=on,
        raw_event_code=info.get("transaction_event_code"),
    )
