"""Reseed the linked issuer with the demo statement.

Plaid's stock sandbox institution returns five merchants repeated monthly,
twelve rows at exactly $500. Every figure Pointwise derives from that is
correct and reads as invented, which is the worst of both. This swaps it for
`data/plaid_demo_user.json`: real chains, varied amounts, dates spread over
two months.

Destructive on purpose. It removes whatever is linked now -- at Plaid's end as
well as locally -- because leaving the old item behind means a stale access
token that still answers, and two issuers' worth of duplicate rows in the feed.

    PYTHONPATH=src .venv/bin/python scripts/seed_plaid_demo.py

Sandbox only. It refuses to run anywhere else.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

from pointwise import plaid_store
from pointwise.plaid import PlaidClient, PlaidNotConfigured
from pointwise.plaid_store import LinkedAccount, PlaidLink
from pointwise.routes_plaid import _cache_row, _is_scorable
from pointwise.state import BY_ID

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "plaid_demo_user.json"

#: Which card each override account is. Order matters: Plaid returns the
#: accounts in the order the config declares them, and both arrive named
#: "Credit card", so there is nothing else to match on. The script checks the
#: mapping afterwards rather than trusting it.
CARDS = ["amex-gold", "capital-one-venture-x"]

#: A merchant that should only ever appear on the first account. If it lands
#: on the second, Plaid returned the accounts in another order and every row
#: is now attributed to the wrong card -- which would silently invert the
#: advice rather than fail.
SENTINEL = ("Apple Store", "amex-gold")

#: A new item answers sync with an empty page while Plaid prepares the feed.
SYNC_ATTEMPTS = 10
SYNC_WAIT_SECONDS = 4


def strip_comments(value):
    """Drop the `_`-prefixed keys the config uses to explain itself."""
    if isinstance(value, dict):
        return {k: strip_comments(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [strip_comments(v) for v in value]
    return value


def main() -> int:
    client = PlaidClient()
    if not client.configured:
        print("Set PLAID_CLIENT_ID and PLAID_SECRET in .env first.", file=sys.stderr)
        return 1
    if not client.config.is_sandbox:
        print(
            f"PLAID_ENV is {client.config.environment!r}. This script only runs "
            "against the sandbox -- it would delete a real linked account.",
            file=sys.stderr,
        )
        return 1

    for card_id in CARDS:
        if card_id not in BY_ID:
            print(f"No card {card_id!r} in the corpus.", file=sys.stderr)
            return 1

    config = strip_comments(json.loads(CONFIG.read_text()))
    declared = sum(len(a.get("transactions", [])) for a in config["override_accounts"])
    print(f"config: {len(config['override_accounts'])} accounts, {declared} transactions")

    # ---------------------------------------------------------- tear down
    existing = plaid_store.read()
    for link in existing.links:
        try:
            client.remove_item(link.access_token)
            print(f"removed item {link.item_id} at Plaid")
        except httpx.HTTPStatusError as exc:
            # Already gone at their end is fine; drop it locally regardless.
            print(f"  (Plaid would not remove {link.item_id}: {exc.response.text[:90]})")
        plaid_store.unlink(link.item_id)
    plaid_store.write_cache([])

    # ------------------------------------------------------------ create
    try:
        public_token = client.create_sandbox_item(custom_user=config)
        tokens = client.exchange(public_token)
        access_token = tokens["access_token"]
        accounts = [a for a in client.accounts(access_token) if a.is_credit_card]
    except PlaidNotConfigured as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as exc:
        print(f"Plaid rejected the request: {exc.response.text}", file=sys.stderr)
        return 1

    if len(accounts) != len(CARDS):
        print(
            f"Expected {len(CARDS)} credit accounts, got {len(accounts)}. "
            "Check override_accounts in the config.",
            file=sys.stderr,
        )
        return 1

    # Cosmetic, so a lookup failure must not abort a reseed that otherwise
    # worked. The screen says which bank is connected; a generic name there is
    # a blemish, a failed reseed an hour before a demo is not.
    try:
        bank = client.institution_name(access_token) or "Connected bank"
    except httpx.HTTPStatusError:
        bank = "Connected bank"

    link = PlaidLink(
        item_id=tokens.get("item_id", public_token[:24]),
        access_token=access_token,
        institution_name=bank,
        accounts=tuple(
            LinkedAccount(account_id=a.account_id, label=a.label, card_id=card_id)
            for a, card_id in zip(accounts, CARDS)
        ),
    )
    plaid_store.upsert(link)
    for a, card_id in zip(accounts, CARDS):
        print(f"mapped {a.label} -> {BY_ID[card_id].name}")

    # -------------------------------------------------------------- sync
    # A freshly created item answers /transactions/sync with an empty page and
    # has_more false while Plaid is still preparing the feed -- indistinguish-
    # able from an account with no spend. In production you would wait for the
    # SYNC_UPDATES_AVAILABLE webhook; a script with no public URL polls.
    tracked = {a.account_id for a in link.accounts}
    cursor, added, skipped = None, [], 0
    for attempt in range(1, SYNC_ATTEMPTS + 1):
        while True:
            page = client.sync(access_token, cursor)
            keep = [t for t in page["added"] if _is_scorable(t, tracked)]
            skipped += len(page["added"]) - len(keep)
            added.extend(keep)
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
        # Stopping at the first non-empty page banks whatever happened to be
        # ready, which is how a 22-row statement quietly becomes 15. The
        # declared count is known, so wait for it rather than guess.
        if len(added) >= declared:
            break
        if attempt < SYNC_ATTEMPTS:
            print(
                f"  {len(added)}/{declared} transactions so far, "
                f"waiting ({attempt}/{SYNC_ATTEMPTS})"
            )
            time.sleep(SYNC_WAIT_SECONDS)
    plaid_store.set_cursor(link.item_id, cursor)
    plaid_store.merge_cache([_cache_row(t, link) for t in added], [], [])

    # ------------------------------------------------------------ verify
    rows = plaid_store.read_cache()
    if len(rows) < declared:
        print(
            f"\n!! Declared {declared} transactions, cached {len(rows)}. "
            "A short feed is usually the history window: Plaid will not return "
            "a row older than days_requested, which is fixed at item creation.",
            file=sys.stderr,
        )
        return 1

    by_card = {a.account_id: a.card_id for a in link.accounts}
    merchant, expected = SENTINEL
    landed = {by_card.get(r.account_id) for r in rows if merchant in r.merchant_name}
    if not landed:
        print(
            f"\n!! {merchant} is not in the {len(rows)} rows that came back, so "
            "the account-to-card mapping could not be checked. Look at the feed "
            "before trusting it.",
            file=sys.stderr,
        )
        return 1
    if landed != {expected}:
        print(
            f"\n!! {merchant} landed on {landed} but belongs to {expected!r}. "
            "Plaid returned the accounts in a different order, so every row is "
            "attributed to the wrong card. Fix CARDS and reseed.",
            file=sys.stderr,
        )
        return 1

    print(f"\ncached {len(rows)} rows, skipped {skipped} non-purchases")
    print(f"sentinel ok: {merchant} is on {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
