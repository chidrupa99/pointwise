"""Process-wide singletons the routers share.

The card corpus, the place provider, the PayPal client and the chat advisor are
each built once at import. They live here rather than in `api.py` so the route
modules can reach them without importing the app -- which would be circular --
and so a test can swap one out in one obvious place.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import httpx

from .activity import RawActivity, load_demo_activity
from .agent import Advisor
from .loader import load_cards
from .models import Card, CardState
from .paypal import PayPalClient, PayPalNotConfigured
from .places import FixturePlaceProvider
from .recommend import card_states
from . import ledger, plaid_store, wallet

#: Every card the app knows how to price. This is the catalog the add-card
#: picker browses -- NOT the user's wallet.
CATALOG = load_cards()
BY_ID = {card.id: card for card in CATALOG}
PLACES = FixturePlaceProvider()
PAYPAL = PayPalClient()


def my_cards() -> list[Card]:
    """The cards the user actually holds.

    Read fresh on every call rather than captured at import, because adding a
    card has to change the next recommendation -- not the next restart.
    """
    return wallet.owned(CATALOG)


#: Both sources are passed as functions so the advisor sees the wallet and the
#: feed as they are when a question is asked. Capturing either at import time
#: would let the chat and the home screen disagree the moment a card is added.
ADVISOR = Advisor(
    places=PLACES,
    cards_source=my_cards,
    activity_source=lambda: activity_feed()[0],
)


def build_states(
    category: str, spend_to_date: Decimal = Decimal("0"), activated: list[str] | None = None
) -> dict[str, CardState]:
    """Apply simulated usage to any capped rule covering this category."""
    return card_states(my_cards(), category, spend_to_date, activated or [])


def activity_feed() -> tuple[list[RawActivity], str]:
    """Posted transactions, from PayPal when connected and fixtures otherwise.

    The source is returned alongside so the UI can be honest about which it is
    showing rather than passing fixtures off as real spend.
    """
    remote: list[RawActivity] = []
    if PAYPAL.configured:
        try:
            end = date.today()
            found = PAYPAL.list_transactions(end - timedelta(days=30), end)
            remote = [
                RawActivity(
                    transaction_id=t.transaction_id,
                    merchant_name=t.merchant_name,
                    amount=t.amount,
                    on=t.on,
                    card_id=None,
                    source="paypal",
                )
                for t in found
            ]
        except (PayPalNotConfigured, httpx.HTTPError, ValueError, KeyError):
            # Fall through rather than showing the user an empty app because a
            # third party had a bad minute.
            remote = []

    # Our own purchases are authoritative and immediate: Transaction Search
    # lags by up to ~3 hours and never says which card funded a payment.
    mine = [
        RawActivity(
            transaction_id=e.transaction_id,
            merchant_name=e.merchant_name,
            amount=e.amount,
            on=e.on,
            card_id=e.card_id,
            source="pointwise",
            recorded_at=e.recorded_at,
        )
        for e in ledger.read()
    ]

    # Plaid reads the card's own statement, so it sees spending made any way at
    # all -- which is the only source that can answer "which card?" for a
    # purchase this app did not route.
    linked = [
        RawActivity(
            transaction_id=r.transaction_id,
            merchant_name=r.merchant_name,
            amount=Decimal(r.amount),
            on=date.fromisoformat(r.on),
            card_id=r.card_id,
            source="plaid",
            category_hint=r.category_detailed,
        )
        for r in plaid_store.read_cache()
        # A non-positive amount is a refund or a credit, and `Purchase`
        # requires a positive one -- so one stale row of that shape does not
        # merely add noise, it raises inside score() and takes the whole home
        # screen down with a 500. The sync filters these out now; this keeps a
        # cache written before that fix from crashing the app.
        if not r.pending and Decimal(r.amount) > 0
    ]

    seen = {e.transaction_id for e in mine}
    # A purchase routed through our own checkout ALSO posts to the card, so
    # Plaid will report it under a different id. Matching on what both sources
    # agree about -- card, amount, day -- keeps it from being counted twice.
    # This is approximate: two identical coffees on one card on one day would
    # collapse into one. The alternative, double-counting a miss, is worse.
    fingerprints = {(e.card_id, e.amount, e.on) for e in mine}
    linked = [r for r in linked if (r.card_id, r.amount, r.on) not in fingerprints]

    combined = (
        mine
        + linked
        + [r for r in remote if r.transaction_id not in seen]
    )

    if combined:
        present = [
            name
            for name, rows in (("plaid", linked), ("pointwise", mine), ("paypal", remote))
            if rows
        ]
        return combined, "+".join(present)
    return load_demo_activity(), "fixture"
