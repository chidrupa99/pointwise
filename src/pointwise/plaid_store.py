"""What we remember about a linked issuer.

Three things, and each is here for a reason:

  access_token  a long-lived credential to someone's bank data. Server-side
                only -- it must never reach the app, a log line or a repo.
  cursor        where the incremental feed left off. Lose it and the next sync
                re-reads the whole history and duplicates every row.
  mapping       which Plaid account is which card in the wallet. Without it a
                transaction has an account id and no rate to price it with.

The mapping is the interesting one. Plaid says "Platinum Card ••3210"; the
corpus says `amex-platinum`. Nothing guarantees those line up, so the user
confirms the match and this file records what they said.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "plaid.json"


class LinkedAccount(BaseModel):
    """One Plaid account and the card the user says it is."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    label: str
    #: None until the user confirms which catalog card this is. Unmapped
    #: accounts are carried rather than dropped so the confirm screen can
    #: still show them, but their transactions cannot be scored.
    card_id: str | None = None


class PlaidLink(BaseModel):
    """A connected issuer."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    access_token: str
    institution_name: str = "Sandbox bank"
    accounts: tuple[LinkedAccount, ...] = ()
    cursor: str | None = None
    linked_at: datetime = Field(default_factory=datetime.now)

    def card_for(self, account_id: str) -> str | None:
        for a in self.accounts:
            if a.account_id == account_id:
                return a.card_id
        return None

    @property
    def mapped_count(self) -> int:
        return sum(1 for a in self.accounts if a.card_id)


class PlaidState(BaseModel):
    """Every linked issuer. One is enough for the demo; the shape allows more."""

    model_config = ConfigDict(frozen=True)

    links: tuple[PlaidLink, ...] = ()

    @property
    def connected(self) -> bool:
        return bool(self.links)


def read(path: Path | str | None = None) -> PlaidState:
    target = Path(path or STORE_PATH)
    if not target.exists():
        return PlaidState()
    try:
        return PlaidState.model_validate(json.loads(target.read_text()))
    except (json.JSONDecodeError, ValueError):
        # A corrupt store must not take the app down. Treat it as not linked;
        # the user can connect again.
        return PlaidState()


def write(state: PlaidState, path: Path | str | None = None) -> PlaidState:
    """Replace the store atomically, with owner-only permissions.

    The file holds a bank credential. A temp file plus rename means an
    interrupted write cannot truncate it, and 0600 keeps it out of reach of
    other accounts on a shared machine.
    """
    target = Path(path or STORE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(state.model_dump_json(indent=2))
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return state


def upsert(link: PlaidLink, path=None) -> PlaidState:
    """Add or replace a link, keyed on item id."""
    current = read(path)
    others = tuple(li for li in current.links if li.item_id != link.item_id)
    return write(PlaidState(links=others + (link,)), path)


def set_mapping(item_id: str, account_id: str, card_id: str | None, path=None) -> PlaidState:
    """Record which card an account is, or clear it."""
    current = read(path)
    links = []
    for link in current.links:
        if link.item_id != item_id:
            links.append(link)
            continue
        accounts = tuple(
            a.model_copy(update={"card_id": card_id}) if a.account_id == account_id else a
            for a in link.accounts
        )
        links.append(link.model_copy(update={"accounts": accounts}))
    return write(PlaidState(links=tuple(links)), path)


def set_cursor(item_id: str, cursor: str | None, path=None) -> PlaidState:
    current = read(path)
    links = tuple(
        link.model_copy(update={"cursor": cursor}) if link.item_id == item_id else link
        for link in current.links
    )
    return write(PlaidState(links=links), path)


def unlink(item_id: str, path=None) -> PlaidState:
    """Forget an issuer, credential and all."""
    current = read(path)
    return write(
        PlaidState(links=tuple(li for li in current.links if li.item_id != item_id)),
        path,
    )


def redacted(link: PlaidLink) -> dict:
    """A link as the app may see it: everything except the credential.

    The access token never leaves the server. Returning its length is enough
    to prove one is held without putting it on a wire.
    """
    return {
        "item_id": link.item_id,
        "institution_name": link.institution_name,
        "linked_at": link.linked_at.isoformat(timespec="seconds"),
        "has_cursor": link.cursor is not None,
        "access_token_length": len(link.access_token),
        "accounts": [
            {"account_id": a.account_id, "label": a.label, "card_id": a.card_id}
            for a in link.accounts
        ],
    }


# --------------------------------------------------------------- transactions
#
# Synced rows are cached on disk rather than re-fetched per request. The feed is
# incremental and cursor-based: Plaid will not hand back a row twice, so the
# cache IS the record. Re-reading on every page load would also mean a network
# round trip between a user tapping Activity and seeing anything.

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "plaid_transactions.json"


class CachedTransaction(BaseModel):
    """A synced transaction, already resolved to one of the user's cards."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    account_id: str
    card_id: str | None
    merchant_name: str
    amount: str
    on: str
    category_primary: str | None = None
    category_detailed: str | None = None
    pending: bool = False


def read_cache(path: Path | str | None = None) -> list[CachedTransaction]:
    target = Path(path or CACHE_PATH)
    if not target.exists():
        return []
    try:
        raw = json.loads(target.read_text())
        return [CachedTransaction.model_validate(r) for r in raw.get("transactions", [])]
    except (json.JSONDecodeError, ValueError):
        return []


def write_cache(rows: list[CachedTransaction], path: Path | str | None = None) -> None:
    target = Path(path or CACHE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(
                {
                    "_comment": "Synced from Plaid. Derived data; safe to delete.",
                    "transactions": [r.model_dump() for r in rows],
                },
                handle,
                indent=2,
            )
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def merge_cache(
    added: list[CachedTransaction],
    modified: list[CachedTransaction] | None = None,
    removed: list[str] | None = None,
    path=None,
) -> list[CachedTransaction]:
    """Apply one sync page to the cache.

    Plaid's sync returns three lists and all three matter: a pending charge
    becomes a posted one through `modified` (often with a different amount),
    and a reversed charge arrives in `removed`. Treating only `added` would
    leave the audit scoring amounts that no longer exist.
    """
    by_id = {r.transaction_id: r for r in read_cache(path)}
    for row in added:
        by_id[row.transaction_id] = row
    for row in modified or []:
        by_id[row.transaction_id] = row
    for tid in removed or []:
        by_id.pop(tid, None)
    rows = sorted(by_id.values(), key=lambda r: (r.on, r.transaction_id), reverse=True)
    write_cache(rows, path)
    return rows
