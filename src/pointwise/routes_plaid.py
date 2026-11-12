"""Linking a card issuer, and pulling its transactions.

Two ways in. Hosted Link is the real one -- a Plaid-hosted page opened in a web
view, because the app runs in Expo Go which cannot load Plaid's native SDK. The
sandbox shortcut mints a linked item server-side with no UI at all, which is
what a demo should use: it exercises exchange, accounts and sync identically
while removing a login form from the middle of a presentation.

The access token never appears in a response. `plaid_store.redacted` is the
only shape that leaves this module.
"""

from __future__ import annotations

import time
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import plaid_store, wallet
from .plaid import PlaidClient, PlaidNotConfigured
from .plaid_store import CachedTransaction, LinkedAccount, PlaidLink
from .state import BY_ID

router = APIRouter()

PLAID = PlaidClient()


@router.get("/api/plaid/status")
def plaid_status() -> dict:
    """Whether an issuer is linked, and whether one could be."""
    state = plaid_store.read()
    cache = plaid_store.read_cache()
    return {
        "configured": PLAID.configured,
        "environment": PLAID.config.environment,
        "hint": (
            None
            if PLAID.configured
            else "Set PLAID_CLIENT_ID and PLAID_SECRET in .env. A sandbox key "
            "pair from dashboard.plaid.com is free and needs no bank."
        ),
        "sandbox_shortcut_available": PLAID.configured and PLAID.config.is_sandbox,
        "connected": state.connected,
        "links": [plaid_store.redacted(li) for li in state.links],
        "transactions_cached": len(cache),
        "unmapped_accounts": sum(
            1 for li in state.links for a in li.accounts if a.card_id is None
        ),
    }


@router.post("/api/plaid/link-token")
def link_token() -> dict:
    """A Plaid-hosted Link URL to open in a web view."""
    try:
        body = PLAID.create_link_token()
    except PlaidNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Plaid rejected the request: {exc.response.text}"
        ) from exc
    return {
        "link_token": body.get("link_token"),
        "hosted_link_url": (body.get("hosted_link_url") or None),
        "expiration": body.get("expiration"),
    }


class ExchangeRequest(BaseModel):
    public_token: str = Field(min_length=10)


@router.post("/api/plaid/exchange", status_code=201)
def exchange(req: ExchangeRequest) -> dict:
    """Finish a Link flow: swap the public token and read the accounts."""
    return _link_from_public_token(req.public_token)


@router.post("/api/plaid/sandbox-link", status_code=201)
def sandbox_link() -> dict:
    """Link Plaid's test institution directly, with no Link UI.

    Sandbox only. The resulting item carries credit card accounts and a month
    of transactions, which is the whole point.
    """
    if not PLAID.config.is_sandbox:
        raise HTTPException(
            status_code=400,
            detail="The sandbox shortcut only works in the sandbox environment.",
        )
    try:
        public_token = PLAID.create_sandbox_item()
    except PlaidNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Plaid rejected the request: {exc.response.text}"
        ) from exc
    return _link_from_public_token(public_token)


def _link_from_public_token(public_token: str) -> dict:
    try:
        tokens = PLAID.exchange(public_token)
        access_token = tokens["access_token"]
        accounts = PLAID.accounts(access_token)
    except PlaidNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (httpx.HTTPStatusError, KeyError) as exc:
        raise HTTPException(status_code=502, detail=f"Plaid link failed: {exc}") from exc

    # Only credit cards are offered for mapping. A linked login usually brings
    # chequing and savings along, and neither can win a recommendation.
    cards = [a for a in accounts if a.is_credit_card]

    # Cosmetic, so it must not be able to fail a good link. A connected bank
    # with a slightly generic name beats an error on a connection that worked.
    try:
        name = PLAID.institution_name(access_token)
    except (httpx.HTTPStatusError, PlaidNotConfigured, KeyError):
        name = None

    link = PlaidLink(
        item_id=tokens.get("item_id", public_token[:24]),
        access_token=access_token,
        **({"institution_name": name} if name else {}),
        accounts=tuple(
            LinkedAccount(account_id=a.account_id, label=a.label, card_id=_guess(a.label))
            for a in cards
        ),
    )
    plaid_store.upsert(link)

    # Pull the statement now, as part of connecting. A bank that is linked but
    # holds no transactions is not a thing a user can do anything with, and
    # asking them to press "sync" afterwards is asking them to finish our job:
    # connecting a bank means "go and get my history", not "open a pipe".
    pulled = _pull_all(attempts=FIRST_PULL_ATTEMPTS)

    return {
        "linked": True,
        "link": plaid_store.redacted(link),
        "credit_accounts": len(cards),
        "other_accounts": len(accounts) - len(cards),
        # Zero is not a failure. A brand new item answers with an empty page
        # while Plaid prepares the feed, so the caller is told what arrived
        # rather than being left to assume.
        "transactions": pulled.get("transactions_cached", 0),
    }


def _guess(label: str) -> str | None:
    """A first guess at which catalog card an account label names.

    Deliberately weak and always shown to the user for confirmation. Plaid says
    "Platinum Card ••3210" and the corpus says `amex-platinum`; a guess that
    silently mapped the wrong card would mis-price every purchase on it, so
    this only fires when the whole card name appears in the label.
    """
    lowered = label.lower()
    for card in BY_ID.values():
        if card.name.lower() in lowered:
            return card.id
    return None


class MapRequest(BaseModel):
    item_id: str
    account_id: str
    #: None clears the mapping, which is how a user says "not one of mine".
    card_id: str | None = None


@router.post("/api/plaid/map")
def map_account(req: MapRequest) -> dict:
    """Record which card a linked account actually is, and hold that card.

    Saying "this account is my Amex Gold" is the user telling us they carry an
    Amex Gold. Before, it only taught the scorer how to price the rows, and the
    card itself stayed out of the wallet unless they had also added it by hand
    from the catalogue -- two journeys asking the same question, with the user
    left to reconcile them.

    Adding only, never removing. Clearing a mapping means "this account is not
    one of those", which is a statement about the account; the card may still
    be in their pocket, added by hand, and dropping it would delete something
    they told us separately.
    """
    if req.card_id is not None and req.card_id not in BY_ID:
        raise HTTPException(status_code=404, detail=f"No card {req.card_id!r}")
    state = plaid_store.read()
    if not any(li.item_id == req.item_id for li in state.links):
        raise HTTPException(status_code=404, detail="No such linked item")
    updated = plaid_store.set_mapping(req.item_id, req.account_id, req.card_id)
    if req.card_id is not None:
        # No open date: the statement cannot say when the account was opened,
        # and a guessed one would put a false welcome-offer deadline on the
        # tile. `wallet.add` keeps any date already recorded by hand.
        wallet.add(req.card_id)
    _reprice()
    return {"links": [plaid_store.redacted(li) for li in updated.links]}


#: How many times a fresh link asks for the feed before giving up and letting
#: the user pull to refresh. Plaid answers a new item with an empty page while
#: it prepares the transactions; waiting a little beats handing back an empty
#: account, and a long wait behind a tap is worse than either.
FIRST_PULL_ATTEMPTS = 3
FIRST_PULL_WAIT_SECONDS = 2.0


@router.post("/api/plaid/sync")
def sync() -> dict:
    """Pull new transactions for every linked issuer.

    Connecting already does this. What is left for this endpoint is refreshing
    -- the pull-to-refresh on the activity screen, and the retry when a brand
    new item had nothing ready yet.
    """
    state = plaid_store.read()
    if not state.connected:
        raise HTTPException(status_code=409, detail="No issuer is linked.")
    return _pull_all()


def _pull_all(attempts: int = 1) -> dict:
    """Read every linked issuer's new transactions into the cache.

    `attempts` is for a just-created item only. Retrying an established link
    cannot help: the cursor has already advanced past everything Plaid holds,
    so the second pass is guaranteed to be empty and only costs the caller
    time.
    """
    added = modified = removed = skipped = 0
    for attempt in range(attempts):
        if attempt:
            time.sleep(FIRST_PULL_WAIT_SECONDS)
        # Re-read: the cursor moved in the previous attempt.
        for link in plaid_store.read().links:
            counts = _pull_link(link)
            added += counts["added"]
            modified += counts["modified"]
            removed += counts["removed"]
            skipped += counts["skipped"]
        if added:
            break

    cache = plaid_store.read_cache()
    return {
        "added": added,
        "modified": modified,
        "removed": removed,
        # Rows that are not purchases on a tracked card: other accounts on the
        # same login, card payments, transfers, refunds. Reported rather than
        # hidden, so a surprising count is visible.
        "skipped": skipped,
        "transactions_cached": len(cache),
        "unmapped": sum(1 for r in cache if r.card_id is None),
    }


def _pull_link(link: PlaidLink) -> dict:
    """One issuer's pages, from its stored cursor to the end of the feed."""
    added = modified = removed = skipped = 0
    cursor = link.cursor
    tracked = {a.account_id for a in link.accounts}
    # Plaid pages; keep going until it says there is no more. The cursor is
    # persisted each round so an interruption resumes rather than restarts.
    while True:
        try:
            page = PLAID.sync(link.access_token, cursor)
        except PlaidNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502, detail=f"Plaid sync failed: {exc.response.text}"
            ) from exc

        keep_added = [t for t in page["added"] if _is_scorable(t, tracked)]
        keep_modified = [t for t in page["modified"] if _is_scorable(t, tracked)]
        plaid_store.merge_cache(
            [_cache_row(t, link) for t in keep_added],
            [_cache_row(t, link) for t in keep_modified],
            page["removed"],
        )
        added += len(keep_added)
        modified += len(keep_modified)
        removed += len(page["removed"])
        skipped += (len(page["added"]) - len(keep_added)) + (
            len(page["modified"]) - len(keep_modified)
        )
        cursor = page["next_cursor"]
        plaid_store.set_cursor(link.item_id, cursor)
        if not page["has_more"]:
            break
    return {
        "added": added,
        "modified": modified,
        "removed": removed,
        "skipped": skipped,
    }


#: Plaid categories that are not purchases. A credit card payment is money
#: leaving a bank account to settle the card -- auditing it would produce
#: "you should have put your card payment on a different card", which is
#: nonsense. Transfers and interest are the same kind of noise.
NOT_A_PURCHASE = frozenset(
    {"LOAN_PAYMENTS", "TRANSFER_IN", "TRANSFER_OUT", "BANK_FEES", "INCOME"}
)


def _is_scorable(t, tracked: set[str]) -> bool:
    """Whether a Plaid row is a purchase this app can audit.

    Three filters, each found by pointing the code at the real sandbox rather
    than a fake:

    - A linked login carries chequing and savings too. Thirty of the first
      forty-eight rows were from accounts that are not cards at all.
    - Card payments and transfers are not purchases.
    - A negative amount is a refund, a credit or interest. `Purchase` requires
      a positive amount, so one of these does not merely add noise -- it
      raises, and the whole activity screen returns a 500.
    """
    if t.account_id not in tracked:
        return False
    if t.amount <= 0:
        return False
    return (t.category_primary or "") not in NOT_A_PURCHASE


def _cache_row(t, link: PlaidLink) -> CachedTransaction:
    return CachedTransaction(
        transaction_id=t.transaction_id,
        account_id=t.account_id,
        card_id=link.card_for(t.account_id),
        merchant_name=t.best_name,
        amount=str(t.amount),
        on=t.on.isoformat(),
        category_primary=t.category_primary,
        category_detailed=t.category_detailed,
        pending=t.pending,
    )


def _reprice() -> None:
    """Re-apply account mappings to rows already cached.

    Mapping usually happens after the first sync, so without this a user would
    confirm their cards and see the feed stay stubbornly unscored.
    """
    state = plaid_store.read()
    by_account = {
        a.account_id: a.card_id for li in state.links for a in li.accounts
    }
    rows = plaid_store.read_cache()
    plaid_store.write_cache(
        [r.model_copy(update={"card_id": by_account.get(r.account_id)}) for r in rows]
    )


@router.delete("/api/plaid/link/{item_id}")
def remove_link(item_id: str) -> dict:
    """Disconnect a bank: revoke at Plaid, then drop everything local.

    Revoking first is the point. Deleting our own copy while the access token
    stays live at Plaid is not disconnecting, it is losing the receipt -- the
    consent keeps standing and we no longer hold the one credential that could
    withdraw it.

    If Plaid refuses, the local data still goes. The user asked to be
    disconnected, and keeping their transactions to preserve our ability to
    retry would be serving ourselves. What we can do is say so plainly, which
    is what `revoked` is for.
    """
    state = plaid_store.read()
    link = next((li for li in state.links if li.item_id == item_id), None)
    if link is None:
        raise HTTPException(status_code=404, detail="No such linked item")

    revoked = True
    try:
        PLAID.remove_item(link.access_token)
    except (PlaidNotConfigured, httpx.HTTPStatusError):
        revoked = False

    accounts = {a.account_id for a in link.accounts}
    plaid_store.unlink(item_id)
    plaid_store.write_cache(
        [r for r in plaid_store.read_cache() if r.account_id not in accounts]
    )
    return {"unlinked": item_id, "revoked": revoked}


#: Exposed for the activity feed, which must not import a router.
def cached_rows() -> list[CachedTransaction]:
    return plaid_store.read_cache()


def amount_of(row: CachedTransaction) -> Decimal:
    return Decimal(row.amount)
