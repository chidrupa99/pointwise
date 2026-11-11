"""Activity scoring: the audit that turns history into a number."""

from datetime import date
from decimal import Decimal

import pytest

from pointwise.activity import (
    RawActivity,
    Verdict,
    load_demo_activity,
    score,
    score_all,
    wallet_summary,
)
from pointwise.loader import load_cards

D = Decimal


@pytest.fixture(scope="module")
def cards():
    return load_cards()


def test_best_card_used_is_optimal(cards):
    result = score(
        RawActivity(
            transaction_id="t1",
            merchant_name="Trader Joe's",
            amount=D("100"),
            on=date(2026, 10, 20),
            card_id="amex-gold",
        ),
        cards,
    )
    assert result.verdict is Verdict.OPTIMAL
    assert result.missed_dollars == D("0")
    assert result.earned_dollars == result.best_dollars


def test_wrong_card_is_a_miss_with_the_gap(cards):
    """$100 of groceries on 2% instead of Amex Gold's 7.2% leaves $5.20."""
    result = score(
        RawActivity(
            transaction_id="t2",
            merchant_name="Trader Joe's",
            amount=D("100"),
            on=date(2026, 10, 20),
            card_id="citi-double-cash",
        ),
        cards,
    )
    assert result.verdict is Verdict.MISSED
    assert result.earned_dollars == D("2.00")
    assert result.best_dollars == D("7.20")
    assert result.missed_dollars == D("5.20")
    assert result.best_card_name == "Amex Gold"


def test_unknown_funding_source_is_not_scored_as_a_miss(cards):
    """PayPal does not say which card paid. Unknown must not imply failure."""
    result = score(
        RawActivity(
            transaction_id="t3",
            merchant_name="Trader Joe's",
            amount=D("100"),
            on=date(2026, 10, 20),
            card_id=None,
        ),
        cards,
    )
    assert result.verdict is Verdict.UNKNOWN
    assert result.missed_dollars == D("0")
    assert result.card_name is None


def test_walmart_on_a_flat_card_is_optimal(cards):
    """The superstore case: no grocery card wins, so 2x is actually right."""
    result = score(
        RawActivity(
            transaction_id="t4",
            merchant_name="Walmart",
            amount=D("100"),
            on=date(2026, 10, 20),
            card_id="capital-one-venture-x",
        ),
        cards,
    )
    assert result.category == "superstore"
    assert result.verdict is Verdict.OPTIMAL


def test_feed_is_newest_first(cards):
    scored = score_all(load_demo_activity(), cards)
    assert [a.on for a in scored] == sorted((a.on for a in scored), reverse=True)


def test_demo_feed_contains_both_verdicts(cards):
    """A feed that is all green or all amber demonstrates nothing."""
    verdicts = {a.verdict for a in score_all(load_demo_activity(), cards)}
    assert Verdict.OPTIMAL in verdicts
    assert Verdict.MISSED in verdicts


class TestWalletSummary:
    def test_every_card_appears_even_with_no_spend(self, cards):
        scored = score_all(load_demo_activity(), cards)
        summary = wallet_summary(cards, scored)
        assert len(summary) == len(cards)

    def test_totals_match_the_scored_feed(self, cards):
        scored = score_all(load_demo_activity(), cards)
        summary = wallet_summary(cards, scored)
        assert sum(w.missed_dollars for w in summary) == sum(
            a.missed_dollars for a in scored
        )
        assert sum(w.transaction_count for w in summary) == len(
            [a for a in scored if a.card_id]
        )

    def test_points_only_accrue_on_points_cards(self, cards):
        scored = score_all(load_demo_activity(), cards)
        by_id = {w.card_id: w for w in wallet_summary(cards, scored)}
        assert by_id["citi-double-cash"].points_earned == D("0")
        assert by_id["amex-gold"].points_earned > D("0")


class TestAnEmptyWallet:
    """A new user has no cards but PayPal already has their history.

    This path runs on the very first launch, before a single card is added.
    It used to raise and take the whole home screen down with a 500.
    """

    def test_scoring_does_not_raise(self):
        from pointwise.activity import load_demo_activity, score_all

        scored = score_all(load_demo_activity(), [])
        assert len(scored) == len(load_demo_activity())

    def test_every_row_is_unknown_not_optimal(self):
        """With nothing to compare against there is no verdict.

        Calling it optimal would tell a user with no cards that they are
        already playing perfectly.
        """
        from pointwise.activity import Verdict, load_demo_activity, score_all

        for row in score_all(load_demo_activity(), []):
            assert row.verdict is Verdict.UNKNOWN
            assert row.missed_dollars == 0
            assert row.best_card_name is None

    def test_the_wallet_summary_is_empty_not_broken(self):
        from pointwise.activity import load_demo_activity, score_all, wallet_summary

        assert wallet_summary([], score_all(load_demo_activity(), [])) == []


class TestFeedOrdering:
    """A purchase just made must appear above one from this morning.

    `on` is only a date, so same-day rows were tie-broken on transaction id --
    an arbitrary string. The user buys something in the app, looks at the feed,
    and finds it three rows down. That reads as the app having missed it.
    """

    def _row(self, tid, merchant, recorded_at):
        from datetime import date as _date

        from pointwise.activity import RawActivity

        return RawActivity(
            transaction_id=tid,
            merchant_name=merchant,
            amount=Decimal("10"),
            on=_date(2026, 10, 27),
            card_id="amex-gold",
            recorded_at=recorded_at,
        )

    def test_the_newest_recording_sorts_first(self):
        from datetime import datetime

        from pointwise.activity import score_all
        from pointwise.loader import load_cards

        rows = [
            # Deliberately ordered so transaction id alone would get it wrong:
            # the earlier purchase has the alphabetically higher id.
            self._row("ZZZ", "This morning", datetime(2026, 10, 27, 9, 0)),
            self._row("AAA", "Just now", datetime(2026, 10, 27, 16, 30)),
        ]
        feed = score_all(rows, load_cards())
        assert [a.merchant_name for a in feed] == ["Just now", "This morning"]

    def test_untimed_rows_sort_below_timed_ones(self):
        """Fixtures and PayPal's own feed carry no timestamp.

        They are older history by definition, so they belong underneath
        anything this app recorded itself today.
        """
        from datetime import datetime

        from pointwise.activity import score_all
        from pointwise.loader import load_cards

        rows = [
            self._row("ZZZ", "No timestamp", None),
            self._row("AAA", "Recorded by us", datetime(2026, 10, 27, 12, 0)),
        ]
        feed = score_all(rows, load_cards())
        assert feed[0].merchant_name == "Recorded by us"

    def test_date_still_beats_the_timestamp(self):
        """A later day wins regardless of the time of day recorded."""
        from datetime import date as _date
        from datetime import datetime

        from pointwise.activity import RawActivity, score_all
        from pointwise.loader import load_cards

        older_day = RawActivity(
            transaction_id="A",
            merchant_name="Yesterday",
            amount=Decimal("10"),
            on=_date(2026, 10, 26),
            card_id="amex-gold",
            recorded_at=datetime(2026, 10, 27, 23, 0),
        )
        newer_day = self._row("B", "Today", datetime(2026, 10, 27, 1, 0))
        feed = score_all([older_day, newer_day], load_cards())
        assert feed[0].merchant_name == "Today"
