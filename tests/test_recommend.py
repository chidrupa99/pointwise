"""Ranking tests: the answer a user actually sees."""

from datetime import date
from decimal import Decimal

import pytest

from pointwise.loader import load_cards
from pointwise.models import CapUsage, CardState, Purchase
from pointwise.recommend import recommend

D = Decimal


@pytest.fixture(scope="module")
def cards():
    return load_cards()


def test_grocery_winner_is_the_6pct_card(cards):
    """Uncapped, Blue Cash Preferred's 6% beats Amex Gold's 4x at 1.8c (7.2%)?

    No -- 7.2% wins. This asserts the ordering is by value, not by headline rate.
    """
    rec = recommend(
        cards, Purchase(amount=D("200"), category="grocery", on=date(2026, 10, 20))
    )
    assert rec.best.card_id == "amex-gold"
    assert rec.best.net_value_dollars == D("14.40")
    assert rec.runner_up.card_id == "amex-blue-cash-preferred"
    assert rec.runner_up.net_value_dollars == D("12.00")
    assert rec.advantage_dollars == D("2.40")


def test_exhausting_the_winners_cap_changes_the_answer(cards):
    """The recommendation must move when the best card's cap is spent."""
    states = {
        "amex-gold": CardState(
            card_id="amex-gold",
            usage={"amex-gold-grocery": CapUsage(spend_to_date=D("25000"))},
        )
    }
    rec = recommend(
        cards,
        Purchase(amount=D("200"), category="grocery", on=date(2026, 10, 20)),
        states,
    )
    assert rec.best.card_id == "amex-blue-cash-preferred"


def test_superstore_is_not_a_grocery_bonus(cards):
    """Walmart resolves to SUPERSTORE, so no grocery card should win it.

    The honest answer here is a flat-rate card, which is the whole point.
    """
    rec = recommend(
        cards, Purchase(amount=D("200"), category="superstore", on=date(2026, 10, 20))
    )
    assert rec.best.card_id not in {"amex-gold", "amex-blue-cash-preferred"}
    assert rec.best.net_value_dollars == D("6.80")  # Venture X 2x at 1.7c


def test_disqualified_cards_are_excluded_not_ranked(cards):
    states = {
        c.id: CardState(card_id=c.id, available_credit=D("50"))
        for c in cards
        if c.id == "citi-double-cash"
    }
    rec = recommend(
        cards,
        Purchase(amount=D("3000"), category="other", on=date(2026, 10, 20)),
        states,
    )
    assert "citi-double-cash" not in {e.card_id for e in rec.ranked}
    assert "citi-double-cash" in {e.card_id for e in rec.excluded}


def test_ranking_is_stable_across_runs(cards):
    """An unstable order reads as a bug to a user who looks twice."""
    purchase = Purchase(amount=D("100"), category="other", on=date(2026, 10, 20))
    orders = [
        tuple(e.card_id for e in recommend(cards, purchase).ranked) for _ in range(5)
    ]
    assert len(set(orders)) == 1


def test_explain_is_short_and_names_the_gap(cards):
    """This string has to fit a 4 KB Live Activity and a glance."""
    rec = recommend(
        cards, Purchase(amount=D("200"), category="dining", on=date(2026, 10, 20))
    )
    line = rec.explain()
    assert "Amex Gold" in line
    assert "better than" in line
    assert len(line) < 120


def test_every_card_is_ranked_or_excluded(cards):
    rec = recommend(
        cards, Purchase(amount=D("100"), category="dining", on=date(2026, 10, 20))
    )
    assert len(rec.ranked) + len(rec.excluded) == len(cards)
