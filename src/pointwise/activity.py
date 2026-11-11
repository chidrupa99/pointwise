"""Scoring past transactions: what was earned versus what could have been.

This is the audit loop. Each posted transaction is replayed through the engine
with the card that was actually used, then against the whole wallet, and the
difference is the money left on the table.

It is also where the product learns: a posted transaction carries the merchant
that a pre-purchase guess could only predict.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .categories import resolve_category
from .engine import evaluate
from .models import Card, Purchase, RewardUnit
from .recommend import recommend

DEMO_ACTIVITY = Path(__file__).resolve().parents[2] / "data" / "activity.demo.json"

#: Stands in for "we never recorded a time", so those rows sort last.
_EPOCH = datetime(1970, 1, 1)

_ZERO = Decimal("0")


class Verdict(str, Enum):
    """How well the card chosen for a transaction did."""

    OPTIMAL = "optimal"
    MISSED = "missed"
    UNKNOWN = "unknown"


class RawActivity(BaseModel):
    """A transaction before the engine has scored it."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    merchant_name: str
    amount: Decimal
    on: date
    #: Which of the user's cards paid. None when the funding source is unknown,
    #: which is the honest state for anything not routed through our checkout.
    card_id: str | None = None
    source: str = "fixture"
    #: The aggregator's own category for this row, when there is one. Passed
    #: to the resolver as a signal ranked below our merchant map and above
    #: reading words out of a merchant's name.
    category_hint: str | None = None
    #: When Pointwise wrote this down, as distinct from the date it happened.
    #: `on` is only a date, so several purchases in one day are indistinguishable
    #: by it -- and the feed was falling back to transaction id, which is
    #: arbitrary. A purchase made thirty seconds ago has to appear above one
    #: from this morning, or the user thinks the app missed it.
    recorded_at: datetime | None = None


class ScoredActivity(BaseModel):
    """A transaction with the verdict attached."""

    model_config = ConfigDict(frozen=True)

    transaction_id: str
    merchant_name: str
    amount: Decimal
    on: date
    category: str
    provenance: str
    #: Which feed this row came from: "plaid" (the card's own statement),
    #: "pointwise" (a purchase seeded through /api/checkout, which is a demo
    #: harness and not something a user can do), "paypal" or "fixture". The UI
    #: labels them differently because they are not equally real.
    source: str = "fixture"

    card_id: str | None
    card_name: str | None
    earned_dollars: Decimal
    earned_points: Decimal

    #: None only when the wallet is empty -- there is no best card among no
    #: cards, and a placeholder name here would print as advice.
    best_card_id: str | None
    best_card_name: str | None
    best_dollars: Decimal

    missed_dollars: Decimal
    verdict: Verdict


def _points_earned(evaluation) -> Decimal:
    """Points, not dollars, for the per-card totals in the wallet view."""
    return sum(
        (
            c.reward_quantity
            for c in evaluation.components
            if c.unit.value in ("points", "miles")
        ),
        _ZERO,
    )


def score(raw: RawActivity, cards: list[Card]) -> ScoredActivity:
    """Replay one transaction through the engine."""
    by_id = {c.id: c for c in cards}
    category, provenance = resolve_category(
        raw.merchant_name, plaid_detailed=raw.category_hint
    )
    purchase = Purchase(
        amount=raw.amount,
        category=category.value,
        on=raw.on,
        merchant_name=raw.merchant_name,
    )

    ranked = recommend(cards, purchase)
    best = ranked.best
    if best is None:
        # An empty wallet, which is a new user, not a fault. PayPal already
        # holds their transaction history before they add a single card, so
        # this path runs on the very first launch -- raising here took the
        # whole home screen down with a 500. With no card to compare against
        # there is no verdict to give, and the row says so.
        return ScoredActivity(
            transaction_id=raw.transaction_id,
            merchant_name=raw.merchant_name,
            amount=raw.amount,
            on=raw.on,
            category=category.value,
            provenance=provenance,
            source=raw.source,
            card_id=raw.card_id,
            card_name=None,
            earned_dollars=_ZERO,
            earned_points=_ZERO,
            best_card_id=None,
            best_card_name=None,
            best_dollars=_ZERO,
            missed_dollars=_ZERO,
            verdict=Verdict.UNKNOWN,
        )

    used_card = by_id.get(raw.card_id) if raw.card_id else None
    if used_card is None:
        earned_dollars, earned_points, card_name = _ZERO, _ZERO, None
        verdict = Verdict.UNKNOWN
        missed = _ZERO
    else:
        used = evaluate(used_card, purchase)
        earned_dollars = used.net_value_dollars
        earned_points = _points_earned(used)
        card_name = used.card_name
        missed = max(_ZERO, best.net_value_dollars - earned_dollars)
        verdict = Verdict.OPTIMAL if missed == _ZERO else Verdict.MISSED

    return ScoredActivity(
        transaction_id=raw.transaction_id,
        merchant_name=raw.merchant_name,
        amount=raw.amount,
        on=raw.on,
        category=category.value,
        provenance=provenance,
        source=raw.source,
        card_id=raw.card_id,
        card_name=card_name,
        earned_dollars=earned_dollars,
        earned_points=earned_points,
        best_card_id=best.card_id,
        best_card_name=best.card_name,
        best_dollars=best.net_value_dollars,
        missed_dollars=missed,
        verdict=verdict,
    )


def score_all(raws: list[RawActivity], cards: list[Card]) -> list[ScoredActivity]:
    """Score a feed, newest first."""
    scored = [score(r, cards) for r in raws]
    # Newest first: by day, then by when we recorded it, then by id as a last
    # resort. Rows with no timestamp (fixtures, PayPal's own feed) sort below
    # ones we recorded ourselves on the same day, which is the right default --
    # a purchase the user just made through the app belongs at the top.
    by_id = {a.transaction_id: r for a, r in zip(scored, raws)}
    scored.sort(
        key=lambda a: (
            a.on,
            by_id[a.transaction_id].recorded_at or _EPOCH,
            a.transaction_id,
        ),
        reverse=True,
    )
    return scored


class WalletCard(BaseModel):
    """A card as the wallet section shows it."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    name: str
    issuer: str
    annual_fee: Decimal
    point_value_cents: Decimal
    #: What this card pays in, taken from its own base rule. A cashback card
    #: earns no points, so rendering "0 pts" on its tile is not a zero -- it is
    #: a category error, and the tile must show dollars instead. This is how
    #: the UI knows which unit the card's figures belong in.
    reward_unit: RewardUnit
    #: Points attributed from scored activity only. This is what Pointwise has
    #: watched being earned, NOT the issuer's statement balance -- no consumer
    #: API exposes that, so claiming otherwise would be a lie.
    points_earned: Decimal
    value_earned_dollars: Decimal
    transaction_count: int
    missed_dollars: Decimal
    #: The same miss expressed in this card's own points, so a tile does not
    #: put points next to dollars and ask the user to convert between them.
    #:
    #: Read it as an equivalence, not an accrual: the user did not forgo this
    #: many points *of this card*, since the better card earns a different
    #: currency entirely. It is what that lost value is worth in the unit this
    #: tile already shows. The UI must word it that way.
    missed_points: Decimal


def _base_unit(card: Card) -> RewardUnit:
    """The unit a card's figures belong in, from its catch-all rule.

    The base rule is the right one to read: a card's bonus categories may pay
    in anything, but what it pays on everything else is what the card *is*.
    """
    base = next((r for r in card.rules if r.is_catch_all), None)
    return base.unit if base else RewardUnit.POINTS


def wallet_summary(cards: list[Card], scored: list[ScoredActivity]) -> list[WalletCard]:
    """Per-card totals derived from the activity we can actually see."""
    summary: list[WalletCard] = []
    for card in cards:
        mine = [a for a in scored if a.card_id == card.id]
        missed = sum((a.missed_dollars for a in mine), _ZERO)
        summary.append(
            WalletCard(
                card_id=card.id,
                name=card.name,
                issuer=card.issuer,
                annual_fee=card.annual_fee,
                point_value_cents=card.point_value_cents,
                reward_unit=_base_unit(card),
                points_earned=sum((a.earned_points for a in mine), _ZERO),
                value_earned_dollars=sum((a.earned_dollars for a in mine), _ZERO),
                transaction_count=len(mine),
                missed_dollars=missed,
                missed_points=(
                    missed / card.point_value_cents * Decimal("100")
                ).quantize(Decimal("1")),
            )
        )
    summary.sort(key=lambda w: (-w.value_earned_dollars, w.name))
    return summary


def load_demo_activity(path: Path | str | None = None) -> list[RawActivity]:
    raw = json.loads(Path(path or DEMO_ACTIVITY).read_text())
    return [RawActivity.model_validate(entry) for entry in raw["activity"]]
