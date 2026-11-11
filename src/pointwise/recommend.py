"""Ranking: given a wallet and a purchase, which card wins and by how much.

The gap between first and second place is the number that makes a
recommendation worth acting on. "Use the Gold" is ignorable; "use the Gold,
it's $3.60 better" is not.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from .engine import evaluate
from .models import Card, CapUsage, CardEvaluation, CardState, Purchase

_ZERO = Decimal("0")


def card_states(
    cards: list[Card],
    category: str,
    spend_to_date: Decimal = _ZERO,
    activated_rule_ids: tuple[str, ...] | list[str] = (),
) -> dict[str, CardState]:
    """Per-card state for one category, from what a caller can actually know.

    Applies the same simulated prior spend to every capped rule covering the
    category, which is how cap-crossing is demonstrated without a real
    transaction history. Shared so the API and the chat agent cannot drift into
    answering the same question two different ways.
    """
    activated = frozenset(activated_rule_ids)
    return {
        card.id: CardState(
            card_id=card.id,
            usage={
                rule.id: CapUsage(spend_to_date=spend_to_date)
                for rule in card.rules
                if rule.cap is not None and category in rule.categories
            },
            activated_rule_ids=activated,
        )
        for card in cards
    }


class Recommendation(BaseModel):
    """A ranked answer for one purchase."""

    model_config = ConfigDict(frozen=True)

    purchase: Purchase
    ranked: tuple[CardEvaluation, ...]
    excluded: tuple[CardEvaluation, ...] = ()

    @property
    def best(self) -> CardEvaluation | None:
        return self.ranked[0] if self.ranked else None

    @property
    def runner_up(self) -> CardEvaluation | None:
        return self.ranked[1] if len(self.ranked) > 1 else None

    @property
    def advantage_dollars(self) -> Decimal:
        """How much the winner beats second place by."""
        if self.best is None or self.runner_up is None:
            return _ZERO
        return self.best.net_value_dollars - self.runner_up.net_value_dollars

    def explain(self) -> str:
        """A plain-language line suitable for a notification or the Island.

        Deliberately short: this is the text that has to survive a 4 KB Live
        Activity payload and a glance at a checkout counter.
        """
        if self.best is None:
            return "No eligible card."
        best = self.best
        line = f"{best.card_name} — ${best.net_value_dollars:,.2f} back"
        if self.runner_up is not None and self.advantage_dollars > _ZERO:
            line += (
                f", ${self.advantage_dollars:,.2f} better than "
                f"{self.runner_up.card_name}"
            )
        return line


def recommend(
    cards: list[Card],
    purchase: Purchase,
    states: dict[str, CardState] | None = None,
) -> Recommendation:
    """Rank every card in the wallet for one purchase.

    Ties break on lower annual fee, then on card id, so the ordering is stable
    across runs -- an unstable recommendation reads as a bug to a user who
    checks twice.
    """
    states = states or {}
    fee_by_id = {c.id: c.annual_fee for c in cards}

    evaluations = [evaluate(c, purchase, states.get(c.id)) for c in cards]

    eligible = [e for e in evaluations if not e.disqualified]
    excluded = [e for e in evaluations if e.disqualified]

    eligible.sort(
        key=lambda e: (
            -e.net_value_dollars,
            fee_by_id.get(e.card_id, _ZERO),
            e.card_id,
        )
    )

    return Recommendation(
        purchase=purchase, ranked=tuple(eligible), excluded=tuple(excluded)
    )
