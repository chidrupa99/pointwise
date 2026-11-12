"""Reseed the linked banks with the demo statement.

One item per issuer, because that is how it works in life. A card lives at the
bank that issued it, so an Amex Gold and a Venture X arrive on two separate
connections and can never share a login. Seeding them as two accounts at one
institution made the connect screen tell a story that cannot happen, which is
the kind of detail a reader checks.

Plaid's sandbox will mint items against real institutions -- `ins_10` really
does come back named "American Express" -- so the demo gets true issuer names
instead of First Platypus Bank, while the transactions stay ours.

The statement comes from `data/plaid_demo_user.json`: real chains, varied
amounts, dates spread over two months. Plaid's stock sandbox feed is five
merchants repeated monthly, twelve rows at exactly $500, and every figure
derived from it reads as invented.

Destructive on purpose. It removes whatever is linked now -- at Plaid's end as
well as locally -- because leaving the old items behind means stale access
tokens that still answer, and duplicate rows in the feed.

    PYTHONPATH=src .venv/bin/python scripts/seed_plaid_demo.py

Sandbox only. It refuses to run anywhere else.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from pointwise import plaid_store
from pointwise.plaid import PlaidClient, PlaidNotConfigured
from pointwise.plaid_store import LinkedAccount, PlaidLink
from pointwise.routes_plaid import _cache_row, _is_scorable
from pointwise.state import BY_ID

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "plaid_demo_user.json"


@dataclass(frozen=True)
class Issuer:
    """One bank, one card, one account in the config."""

    institution_id: str
    card_id: str
    #: Which entry of `override_accounts` is this card's statement. The config
    #: stays one list so the rows read together; this is what splits it across
    #: the two connections.
    account_index: int


#: Real institutions, so the screen says American Express rather than the name
#: of a test rig. Both are sandbox-mintable with a custom user.
ISSUERS = [
    Issuer(institution_id="ins_10", card_id="amex-gold", account_index=0),
    Issuer(
        institution_id="ins_128026",
        card_id="capital-one-venture-x",
        account_index=1,
    ),
]

#: A merchant that should only ever appear on the first issuer's card. If it
#: lands anywhere else the config accounts went to the wrong banks and every
#: row is attributed to the wrong card -- which would silently invert the
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


def drain(client: PlaidClient, access_token: str, tracked: set[str], declared: int):
    """Every page Plaid has, waiting for the rows it was told to make.

    A freshly created item answers /transactions/sync with an empty page and
    has_more false while Plaid is still preparing the feed -- indistinguishable
    from an account with no spend. Stopping at the first non-empty page banks
    whatever happened to be ready, which is how a 12-row statement quietly
    becomes 8. The declared count is known, so wait for it rather than guess.

    In production you would wait for the SYNC_UPDATES_AVAILABLE webhook; a
    script with no public URL polls.
    """
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
        if len(added) >= declared:
            break
        if attempt < SYNC_ATTEMPTS:
            print(
                f"    {len(added)}/{declared} so far, "
                f"waiting ({attempt}/{SYNC_ATTEMPTS})"
            )
            time.sleep(SYNC_WAIT_SECONDS)
    return cursor, added, skipped


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

    for issuer in ISSUERS:
        if issuer.card_id not in BY_ID:
            print(f"No card {issuer.card_id!r} in the corpus.", file=sys.stderr)
            return 1

    config = strip_comments(json.loads(CONFIG.read_text()))
    in_config = config["override_accounts"]
    if len(in_config) < len(ISSUERS):
        print(
            f"Config declares {len(in_config)} accounts but {len(ISSUERS)} "
            "issuers need one each.",
            file=sys.stderr,
        )
        return 1
    total_declared = sum(
        len(in_config[i.account_index].get("transactions", [])) for i in ISSUERS
    )
    print(f"config: {len(ISSUERS)} issuers, {total_declared} transactions")

    # ---------------------------------------------------------- tear down
    for link in plaid_store.read().links:
        try:
            client.remove_item(link.access_token)
            print(f"removed item {link.item_id} at Plaid")
        except httpx.HTTPStatusError as exc:
            # Already gone at their end is fine; drop it locally regardless.
            print(f"  (Plaid would not remove {link.item_id}: {exc.response.text[:90]})")
        plaid_store.unlink(link.item_id)
    plaid_store.write_cache([])

    # ------------------------------------------------- one item per issuer
    skipped_total = 0
    for issuer in ISSUERS:
        card = BY_ID[issuer.card_id]
        # One account in, one account out: nothing to match on afterwards and
        # nothing to get into the wrong order.
        one = dict(config)
        one["override_accounts"] = [in_config[issuer.account_index]]
        declared = len(one["override_accounts"][0].get("transactions", []))

        try:
            public_token = client.create_sandbox_item(
                institution_id=issuer.institution_id, custom_user=one
            )
            tokens = client.exchange(public_token)
            access_token = tokens["access_token"]
            accounts = [a for a in client.accounts(access_token) if a.is_credit_card]
            bank = client.institution_name(access_token)
        except PlaidNotConfigured as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except httpx.HTTPStatusError as exc:
            print(
                f"Plaid rejected {issuer.institution_id}: {exc.response.text}",
                file=sys.stderr,
            )
            return 1

        if len(accounts) != 1:
            print(
                f"Expected 1 credit account at {bank or issuer.institution_id}, "
                f"got {len(accounts)}.",
                file=sys.stderr,
            )
            return 1

        account = accounts[0]
        link = PlaidLink(
            item_id=tokens.get("item_id", public_token[:24]),
            access_token=access_token,
            institution_name=bank or "Connected bank",
            accounts=(
                LinkedAccount(
                    account_id=account.account_id,
                    label=account.label,
                    card_id=issuer.card_id,
                ),
            ),
        )
        plaid_store.upsert(link)
        print(f"{bank}: {account.label} -> {card.name}")

        cursor, added, skipped = drain(
            client, access_token, {account.account_id}, declared
        )
        plaid_store.set_cursor(link.item_id, cursor)
        plaid_store.merge_cache([_cache_row(t, link) for t in added], [], [])
        skipped_total += skipped
        print(f"    cached {len(added)}/{declared}, skipped {skipped}")

    # ------------------------------------------------------------ verify
    rows = plaid_store.read_cache()
    if len(rows) < total_declared:
        print(
            f"\n!! Declared {total_declared} transactions, cached {len(rows)}. "
            "A short feed is usually the history window: Plaid will not return "
            "a row older than days_requested, which is fixed at item creation.",
            file=sys.stderr,
        )
        return 1

    by_account = {
        a.account_id: a.card_id for li in plaid_store.read().links for a in li.accounts
    }
    merchant, expected = SENTINEL
    landed = {by_account.get(r.account_id) for r in rows if merchant in r.merchant_name}
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
            "The config accounts went to the wrong issuers, so every row is "
            "attributed to the wrong card. Fix ISSUERS and reseed.",
            file=sys.stderr,
        )
        return 1

    banks = [li.institution_name for li in plaid_store.read().links]
    print(f"\ncached {len(rows)} rows across {len(banks)} banks: {', '.join(banks)}")
    print(f"skipped {skipped_total} non-purchases")
    print(f"sentinel ok: {merchant} is on {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
