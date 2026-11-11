"""Which real funding instrument backs each card in the wallet.

The engine's recommendation is only advice until something actually charges the
right card. This module is the mapping that makes it real: `card_id` ->
a funding source PayPal will accept.

PayPal offers that mapping at three levels of fidelity, and which one is
available depends on what the REST app is authorized for, not on this code:

1. **Vault v3** (`/v3/vault/payment-tokens`) is the one we want. Its token id
   drops straight into `payment_source.card.vault_id` on an Orders v2 order, so
   the engine's pick becomes the funding source for a real capture. It needs
   the "Save payment methods" capability on the app.
2. **Vault v1** (`/v1/vault/credit-cards`) still mints a genuine, PayPal-side
   vault record per card, keyed to our `card_id` via `external_card_id`. The id
   is real and retrievable. It cannot fund an Orders v2 capture, so it gives us
   identity without execution -- useful, and honest about being partial.
3. **An inline test card**, which charges but vaults nothing.

The registry records which level each card got, so nothing downstream can
mistake a sandbox stand-in for a vaulted instrument.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:  # pragma: no cover
    from .models import Card
    from .paypal import PayPalClient

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "funding.json"


class FundingKind(str, Enum):
    """How much of the real thing a card's funding source actually is."""

    #: A Vault v3 payment token. Fundable by Orders v2.
    VAULT_V3 = "vault_v3"
    #: A Vault v1 credit-card record. Real vault id, not fundable by Orders v2.
    VAULT_V1 = "vault_v1"
    #: An inline sandbox test card. Charges, but nothing is stored.
    SANDBOX_CARD = "sandbox_card"

    @property
    def is_vaulted(self) -> bool:
        return self in (FundingKind.VAULT_V3, FundingKind.VAULT_V1)

    @property
    def funds_order_directly(self) -> bool:
        """Whether the stored id itself can be the order's payment source.

        Only v3 can. This is the whole difference between a vault id that is
        merely real and one that actually moves money.
        """
        return self is FundingKind.VAULT_V3


#: PayPal's published sandbox test card numbers, by network. These are not real
#: instruments, are documented publicly, and are only ever sent to PayPal's
#: sandbox host. There is one per network rather than one per card because
#: PayPal publishes one per network; cards sharing a network therefore share a
#: number, and the vault id -- not the number -- is what distinguishes them.
SANDBOX_TEST_CARDS: dict[str, dict[str, str]] = {
    "visa": {"number": "4111111111111111", "type": "visa"},
    "mastercard": {"number": "5555555555554444", "type": "mastercard"},
    "amex": {"number": "378282246310005", "type": "amex"},
    "discover": {"number": "6011111111111117", "type": "discover"},
}

DEFAULT_NETWORK = "visa"
_EXPIRY_MONTH = 1
_EXPIRY_YEAR = 2030


def network_key(card: Card) -> str:
    """The test-card network for a wallet card, defaulting rather than failing.

    A card with no recorded network should still be chargeable in a demo; the
    network only picks which published test number is used.
    """
    key = (card.network or "").strip().lower()
    if key in SANDBOX_TEST_CARDS:
        return key
    if key in ("american express", "amex"):
        return "amex"
    return DEFAULT_NETWORK


class FundingSource(BaseModel):
    """The instrument backing one card."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    kind: FundingKind
    #: PayPal's id for the stored instrument. None for an inline test card.
    vault_id: str | None = None
    network: str
    brand: str | None = None
    last4: str | None = None
    provisioned_on: date | None = None
    #: Why this card did not get a better funding source, when it did not.
    downgrade_reason: str | None = None

    @property
    def label(self) -> str:
        suffix = f" ...{self.last4}" if self.last4 else ""
        if self.vault_id:
            return f"{self.kind.value}:{self.vault_id}{suffix}"
        return f"{self.kind.value}{suffix}"


def _inline_card_payload(card: Card) -> dict[str, str]:
    """An Orders v2 `payment_source.card`, using a published test number."""
    test = SANDBOX_TEST_CARDS[network_key(card)]
    return {
        "number": test["number"],
        "expiry": f"{_EXPIRY_YEAR}-{_EXPIRY_MONTH:02d}",
        "name": card.name[:60],
        "security_code": "1234" if test["type"] == "amex" else "123",
    }


def _vault_v1_payload(card: Card) -> dict[str, object]:
    """A Vault v1 credit-card record, keyed to our card id.

    `external_card_id` is the field that makes the vault record ours: PayPal
    stores it alongside the card, so the mapping survives even if this file
    is lost.
    """
    test = SANDBOX_TEST_CARDS[network_key(card)]
    return {
        "number": test["number"],
        "type": test["type"],
        "expire_month": _EXPIRY_MONTH,
        "expire_year": _EXPIRY_YEAR,
        "first_name": "Pointwise",
        "last_name": card.id[:60],
        "external_card_id": card.id,
        "external_customer_id": "pointwise-demo-user",
    }


def provision(client: PayPalClient, card: Card) -> FundingSource:
    """Get the best funding source PayPal will give us for this card.

    Tries each level in turn and records what it settled for. An authorization
    failure is expected rather than exceptional here -- the whole point is to
    degrade to something that still works -- but a network error is not
    swallowed, because silently handing back a test card when PayPal was simply
    unreachable would hide a real fault.
    """
    net = network_key(card)
    reasons: list[str] = []

    try:
        token = client.vault_card(_inline_card_payload(card), customer_id=card.id)
        source = (token.get("payment_source") or {}).get("card") or {}
        return FundingSource(
            card_id=card.id,
            kind=FundingKind.VAULT_V3,
            vault_id=token.get("id"),
            network=net,
            brand=source.get("brand"),
            last4=source.get("last_digits"),
            provisioned_on=date.today(),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403, 422):
            raise
        reasons.append(f"vault v3 unavailable ({_error_name(exc)})")

    try:
        record = client.vault_card_v1(_vault_v1_payload(card))
        return FundingSource(
            card_id=card.id,
            kind=FundingKind.VAULT_V1,
            vault_id=record.get("id"),
            network=net,
            brand=record.get("type"),
            last4=str(record.get("number", ""))[-4:] or None,
            provisioned_on=date.today(),
            downgrade_reason="; ".join(reasons) or None,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403, 422):
            raise
        reasons.append(f"vault v1 unavailable ({_error_name(exc)})")

    return FundingSource(
        card_id=card.id,
        kind=FundingKind.SANDBOX_CARD,
        network=net,
        last4=SANDBOX_TEST_CARDS[net]["number"][-4:],
        provisioned_on=date.today(),
        downgrade_reason="; ".join(reasons) or None,
    )


def _error_name(exc: httpx.HTTPStatusError) -> str:
    """PayPal's error name, for a log line that says what actually happened."""
    try:
        return str(exc.response.json().get("name", exc.response.status_code))
    except (ValueError, AttributeError):
        return str(exc.response.status_code)


def order_payment_source(card: Card, source: FundingSource | None) -> dict:
    """The `payment_source` for an Orders v2 order on this card.

    A v3 token is passed by reference, which is the real thing: PayPal holds
    the card and we never touch the number. Anything else falls back to the
    published test card for the card's network, because a purchase that cannot
    complete is worse than one completed on a stand-in -- as long as the
    difference is recorded, which `funded_from_vault` is for.
    """
    if source is not None and source.kind.funds_order_directly and source.vault_id:
        return {"card": {"vault_id": source.vault_id}}
    return {"card": _inline_card_payload(card)}


def funded_from_vault(source: FundingSource | None) -> bool:
    """Whether a capture on this source is drawn from the vault.

    False for a v1 record: the id identifies the card but Orders v2 will not
    accept it, so the money came from the inline test card instead. Callers
    must not report a v1 purchase as vault-funded.
    """
    return bool(
        source is not None and source.kind.funds_order_directly and source.vault_id
    )


# ---------------------------------------------------------------- persistence


def read(path: Path | str | None = None) -> dict[str, FundingSource]:
    """The registry, keyed by card id. Missing or corrupt file reads as empty."""
    target = Path(path or REGISTRY_PATH)
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    sources = {}
    for entry in raw.get("sources", []):
        try:
            source = FundingSource.model_validate(entry)
        except ValueError:
            continue  # one bad row should not blank the whole registry
        sources[source.card_id] = source
    return sources


def write(
    sources: dict[str, FundingSource], path: Path | str | None = None
) -> None:
    """Replace the registry atomically."""
    target = Path(path or REGISTRY_PATH)
    payload = {
        "_comment": (
            "card_id -> PayPal funding source. Sandbox instruments only. "
            "Regenerate with scripts/vault_cards.py."
        ),
        "sources": [
            json.loads(s.model_dump_json())
            for s in sorted(sources.values(), key=lambda s: s.card_id)
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
