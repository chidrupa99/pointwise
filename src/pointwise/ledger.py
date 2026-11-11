"""A local record of purchases this app executed.

Transaction Search has a reporting lag -- PayPal documents up to about three
hours before a completed payment appears -- so an app that only reads from it
shows nothing right after a purchase, which is exactly when the user looks.

We also know strictly more about our own purchases than Transaction Search
would tell us: the merchant, and crucially *which card the engine chose*, which
the reporting API never returns. So executed purchases are written here at
capture time, and Transaction Search is for everything that happened elsewhere.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict

LEDGER_PATH = Path(__file__).resolve().parents[2] / "data" / "ledger.json"


class LedgerEntry(BaseModel):
    """One purchase this app put through PayPal."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    order_id: str
    merchant_name: str
    amount: Decimal
    on: date
    #: The card the engine chose. This is the field Transaction Search cannot
    #: give us, and the reason the audit can score our own purchases.
    card_id: str
    capture_status: str
    #: When this row was written, set by whoever appends it. Defaults to None
    #: rather than to `now`: a default_factory cannot distinguish "absent from
    #: the file" from "absent at construction", so reading an older row would
    #: stamp it with the current time -- making ancient history look brand new,
    #: with a different value on every read.
    recorded_at: datetime | None = None
    #: PayPal's id for the stored instrument, when the card has one.
    vault_id: str | None = None
    #: Which tier of funding source paid: see funding.FundingKind. Defaults
    #: cover rows written before the registry existed.
    funding_kind: str = "unknown"
    #: True only when the vault id itself funded the capture. A card can have a
    #: real vault id and still be charged on a stand-in, so these are separate
    #: facts and the audit must not conflate them.
    funded_from_vault: bool = False


def read(path: Path | str | None = None) -> list[LedgerEntry]:
    """Every recorded purchase. Missing or corrupt file reads as empty."""
    target = Path(path or LEDGER_PATH)
    if not target.exists():
        return []
    try:
        raw = json.loads(target.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [LedgerEntry.model_validate(e) for e in raw.get("entries", [])]


def append(entry: LedgerEntry, path: Path | str | None = None) -> None:
    """Add one purchase, writing atomically.

    A half-written ledger would lose the record of a payment that actually
    happened, so the replacement is staged in a temp file and moved into place.
    """
    target = Path(path or LEDGER_PATH)
    entries = read(target)
    entries.append(entry)
    payload = {
        "_comment": "Purchases executed through this app. Written at capture time.",
        "entries": [json.loads(e.model_dump_json()) for e in entries],
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
