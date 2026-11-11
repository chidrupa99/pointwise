"""The wallet, and the welcome-offer deadlines it tracks.

The bonus window is the highest-stakes arithmetic in the product. Everything
else is a comparison between two rates that differ by a few dollars; this is a
cliff edge worth hundreds, and a date computed wrong by one day would push a
user over it while telling them they were fine.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pointwise import wallet
from pointwise.loader import load_cards
from pointwise.models import Provenance, RewardUnit, SignupBonus
from pointwise.wallet import OwnedCard, Wallet

D = Decimal
CATALOG = load_cards()
BY_ID = {c.id: c for c in CATALOG}


@pytest.fixture
def store(tmp_path):
    return tmp_path / "wallet.json"


class TestTheStore:
    def test_a_missing_file_is_a_new_user_not_an_error(self, store):
        """The empty state is a supported state, not a failure."""
        assert wallet.read(store) == Wallet()
        assert wallet.read(store).is_empty is True

    def test_a_corrupt_file_degrades_to_empty(self, store):
        """Better the add-card screen than a crash on launch."""
        store.write_text("{ this is not json")
        assert wallet.read(store).is_empty is True

    def test_add_then_read_round_trips(self, store):
        wallet.add("amex-gold", date(2026, 8, 1), path=store)
        held = wallet.read(store)
        assert held.holds("amex-gold")
        assert held.entry("amex-gold").opened_on == date(2026, 8, 1)

    def test_adding_twice_does_not_duplicate(self, store):
        wallet.add("amex-gold", date(2026, 8, 1), path=store)
        wallet.add("amex-gold", date(2026, 9, 1), path=store)
        held = wallet.read(store)
        assert len(held.cards) == 1
        assert held.entry("amex-gold").opened_on == date(2026, 9, 1)

    def test_re_adding_without_a_date_keeps_the_known_one(self, store):
        """Correcting nothing must not erase what the user already told us."""
        wallet.add("amex-gold", date(2026, 8, 1), path=store)
        wallet.add("amex-gold", path=store)
        assert wallet.read(store).entry("amex-gold").opened_on == date(2026, 8, 1)

    def test_remove(self, store):
        wallet.add("amex-gold", path=store)
        wallet.add("citi-double-cash", path=store)
        wallet.remove("amex-gold", path=store)
        held = wallet.read(store)
        assert not held.holds("amex-gold")
        assert held.holds("citi-double-cash")

    def test_an_unknown_id_is_ignored_when_resolving(self, store):
        """A wallet naming a card the corpus dropped should still open."""
        wallet.write(
            Wallet(cards=(OwnedCard(card_id="amex-gold"), OwnedCard(card_id="gone"))),
            store,
        )
        cards = wallet.owned(CATALOG, wallet.read(store))
        assert [c.id for c in cards] == ["amex-gold"]


class TestTheWindow:
    """Month arithmetic, where the off-by-one deadline bugs live."""

    @pytest.mark.parametrize(
        "opened,months,ends",
        [
            (date(2026, 8, 15), 3, date(2026, 11, 15)),
            # 31 August plus three months is 30 November, not an invalid 31st.
            (date(2026, 8, 31), 3, date(2026, 11, 30)),
            (date(2026, 1, 31), 1, date(2026, 2, 28)),
            (date(2024, 1, 31), 1, date(2024, 2, 29)),
            (date(2026, 12, 15), 3, date(2027, 3, 15)),
            (date(2026, 10, 1), 6, date(2027, 4, 1)),
        ],
    )
    def test_window_end(self, opened, months, ends):
        assert wallet._months_after(opened, months) == ends


def _bonus(points=60000, spend=4000, months=3) -> SignupBonus:
    return SignupBonus(
        points=D(points),
        spend_required=D(spend),
        within_months=months,
        unit=RewardUnit.POINTS,
        provenance=Provenance(),
    )


def _card_with_bonus(bonus: SignupBonus | None):
    return BY_ID["chase-sapphire-preferred"].model_copy(update={"signup_bonus": bonus})


class TestBonusProgress:
    def test_no_offer_means_nothing_to_show(self):
        card = _card_with_bonus(None)
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 1))
        assert wallet.bonus_progress(card, entry, {}) is None

    def test_an_unknown_open_date_means_nothing_to_show(self):
        """A bar at zero would read as 'you have earned nothing'.

        What it would actually mean is 'we do not know when your window
        started', which is a different sentence and must not be rendered as a
        deadline.
        """
        card = _card_with_bonus(_bonus())
        assert wallet.bonus_progress(card, OwnedCard(card_id=card.id), {}) is None

    def test_spend_inside_the_window_counts(self):
        card = _card_with_bonus(_bonus(spend=4000, months=3))
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 15))
        spend = {card.id: [(date(2026, 9, 1), D("1000")), (date(2026, 10, 1), D("500"))]}

        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 10, 27))
        assert p.spent == D("1500")
        assert p.remaining == D("2500")
        assert p.percent == pytest.approx(37.5)
        assert p.window_ends_on == date(2026, 11, 15)
        assert p.days_left == 19
        assert p.earned is False
        assert p.expired is False

    def test_spend_before_the_account_existed_does_not_count(self):
        """The issuer counts from the open date, so neither may we."""
        card = _card_with_bonus(_bonus())
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 15))
        spend = {card.id: [(date(2026, 7, 1), D("5000"))]}

        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 10, 1))
        assert p.spent == D("0")
        assert p.earned is False

    def test_spend_after_the_window_does_not_count(self):
        card = _card_with_bonus(_bonus(months=3))
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 15))
        spend = {card.id: [(date(2026, 12, 1), D("9000"))]}

        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 12, 15))
        assert p.spent == D("0")
        assert p.expired is True

    def test_meeting_the_spend_earns_it(self):
        card = _card_with_bonus(_bonus(spend=4000))
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 15))
        spend = {card.id: [(date(2026, 9, 1), D("4000"))]}

        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 10, 1))
        assert p.earned is True
        assert p.remaining == D("0")
        assert p.percent == 100.0

    def test_earned_beats_expired_forever(self):
        """Once hit, the offer is hit. A later date cannot un-earn it."""
        card = _card_with_bonus(_bonus(spend=4000, months=3))
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 1, 1))
        spend = {card.id: [(date(2026, 2, 1), D("4000"))]}

        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 12, 31))
        assert p.earned is True
        assert p.expired is False

    def test_percent_never_exceeds_one_hundred(self):
        """Overshooting the spend must not render a bar past its end."""
        card = _card_with_bonus(_bonus(spend=1000))
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 15))
        spend = {card.id: [(date(2026, 9, 1), D("9999"))]}

        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 10, 1))
        assert p.percent == 100.0
        assert p.remaining == D("0")

    def test_days_left_floors_at_zero(self):
        card = _card_with_bonus(_bonus(months=3))
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 1, 1))
        p = wallet.bonus_progress(card, entry, {}, today=date(2026, 12, 1))
        assert p.days_left == 0

    def test_another_cards_spend_is_not_counted(self):
        card = _card_with_bonus(_bonus())
        entry = OwnedCard(card_id=card.id, opened_on=date(2026, 8, 15))
        spend = {"amex-gold": [(date(2026, 9, 1), D("9000"))]}
        p = wallet.bonus_progress(card, entry, spend, today=date(2026, 10, 1))
        assert p.spent == D("0")


class TestValuation:
    def test_a_bonus_is_priced_on_the_cards_own_valuation(self):
        card = BY_ID["capital-one-venture-x"]
        # 75,000 miles at this card's cents-per-point.
        assert wallet.value_of(D("75000"), card) == (
            D("75000") * card.point_value_cents / D("100")
        ).quantize(D("0.01"))

    def test_the_seeded_offers_all_price_above_their_spend_hurdle(self):
        """A welcome offer worth less than the spend required to get it would
        be a trap, and would mean the seed data is wrong."""
        for card in CATALOG:
            if card.signup_bonus is None:
                continue
            worth = wallet.value_of(card.signup_bonus.points, card)
            assert worth > 0, card.id
