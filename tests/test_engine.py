"""Engine tests. The cap-crossing cases are the point of the whole module."""

from datetime import date
from decimal import Decimal

import pytest

from pointwise.engine import evaluate
from pointwise.loader import load_cards
from pointwise.models import CapUsage, CardState, Purchase

D = Decimal


@pytest.fixture(scope="module")
def wallet():
    return {c.id: c for c in load_cards()}


def test_simple_cashback(wallet):
    """2% flat on $100 is $2. The floor case."""
    result = evaluate(
        wallet["wells-fargo-active-cash"],
        Purchase(amount=D("100"), category="dining", on=date(2026, 10, 20)),
    )
    assert result.net_value_dollars == D("2.00")
    assert result.effective_rate_percent == D("2.00")
    assert len(result.components) == 1


def test_points_valued_by_cents_per_point(wallet):
    """4x on a card worth 1.8c/pt is 7.2% of spend, not 4%."""
    result = evaluate(
        wallet["amex-gold"],
        Purchase(amount=D("100"), category="dining", on=date(2026, 10, 20)),
    )
    assert result.components[0].reward_quantity == D("400")
    assert result.net_value_dollars == D("7.20")


def test_points_card_can_beat_higher_cashback_rate(wallet):
    """3x at 1.25c/pt (3.75%) beats a 3% cashback rule on the same category."""
    purchase = Purchase(amount=D("100"), category="dining", on=date(2026, 10, 20))
    csp = evaluate(wallet["chase-sapphire-preferred"], purchase)
    flex = evaluate(wallet["chase-freedom-flex"], purchase)
    assert csp.net_value_dollars == D("3.75")
    assert flex.net_value_dollars == D("3.00")
    assert csp.net_value_dollars > flex.net_value_dollars


# ---------------------------------------------------------------- cap splitting


def test_purchase_entirely_under_cap(wallet):
    """6% grocery, $5,000 already spent of a $6,000 cap, $500 purchase fits."""
    card = wallet["amex-blue-cash-preferred"]
    state = CardState(
        card_id=card.id,
        usage={"bcp-grocery": CapUsage(spend_to_date=D("5000"))},
    )
    result = evaluate(
        card,
        Purchase(amount=D("500"), category="grocery", on=date(2026, 10, 20)),
        state,
    )
    assert result.net_value_dollars == D("30.00")  # all 500 at 6%
    assert len(result.components) == 1


def test_purchase_straddles_cap_is_split(wallet):
    """The case a blended rate gets wrong.

    $5,800 of a $6,000 cap used. A $500 grocery purchase earns 6% on the first
    $200 and 1% on the remaining $300 -> $12 + $3 = $15. A naive 6% gives $30,
    and a naive 1% gives $5. Both are wrong.
    """
    card = wallet["amex-blue-cash-preferred"]
    state = CardState(
        card_id=card.id,
        usage={"bcp-grocery": CapUsage(spend_to_date=D("5800"))},
    )
    result = evaluate(
        card,
        Purchase(amount=D("500"), category="grocery", on=date(2026, 10, 20)),
        state,
    )
    assert len(result.components) == 2

    bonus, base = result.components
    assert bonus.spend_applied == D("200.00")
    assert bonus.value_dollars == D("12.00")
    assert base.spend_applied == D("300.00")
    assert base.value_dollars == D("3.00")

    assert result.net_value_dollars == D("15.00")
    assert result.effective_rate_percent == D("3.00")
    assert any("cap reached" in c for c in result.caveats)


def test_fully_consumed_cap_falls_to_base(wallet):
    card = wallet["amex-blue-cash-preferred"]
    state = CardState(
        card_id=card.id,
        usage={"bcp-grocery": CapUsage(spend_to_date=D("6000"))},
    )
    result = evaluate(
        card,
        Purchase(amount=D("200"), category="grocery", on=date(2026, 10, 20)),
        state,
    )
    assert len(result.components) == 1
    assert result.components[0].rule_id == "bcp-base"
    assert result.net_value_dollars == D("2.00")


def test_cap_split_on_a_points_card(wallet):
    """Amex Gold grocery: $24,900 of $25,000 used, $300 purchase.

    $100 at 4x = 400 pts, $200 at 1x = 200 pts, 600 pts at 1.8c = $10.80.
    """
    card = wallet["amex-gold"]
    state = CardState(
        card_id=card.id,
        usage={"amex-gold-grocery": CapUsage(spend_to_date=D("24900"))},
    )
    result = evaluate(
        card,
        Purchase(amount=D("300"), category="grocery", on=date(2026, 10, 20)),
        state,
    )
    assert [c.reward_quantity for c in result.components] == [D("400"), D("200")]
    assert result.net_value_dollars == D("10.80")


def test_no_state_means_unconstrained(wallet):
    """A first-run user who has entered nothing gets the uncapped rate."""
    result = evaluate(
        wallet["amex-blue-cash-preferred"],
        Purchase(amount=D("500"), category="grocery", on=date(2026, 10, 20)),
    )
    assert result.net_value_dollars == D("30.00")


# ------------------------------------------------------------- rotating / gating


def test_rotating_category_inactive_quarter(wallet):
    """A Q4 rotating rule must not pay out in July."""
    card = wallet["chase-freedom-flex"]
    state = CardState(card_id=card.id, activated_rule_ids=frozenset({"flex-rotating-q4-grocery"}))
    result = evaluate(
        card,
        Purchase(amount=D("100"), category="grocery", on=date(2026, 7, 15)),
        state,
    )
    assert result.net_value_dollars == D("1.00")
    assert any("not active in Q3" in c for c in result.caveats)


def test_rotating_category_active_and_activated(wallet):
    card = wallet["chase-freedom-flex"]
    state = CardState(card_id=card.id, activated_rule_ids=frozenset({"flex-rotating-q4-grocery"}))
    result = evaluate(
        card,
        Purchase(amount=D("100"), category="grocery", on=date(2026, 10, 20)),
        state,
    )
    assert result.net_value_dollars == D("5.00")


def test_rotating_category_not_activated_earns_base(wallet):
    """Forgetting to activate is the most common way users lose money."""
    card = wallet["chase-freedom-flex"]
    result = evaluate(
        card,
        Purchase(amount=D("100"), category="grocery", on=date(2026, 10, 20)),
        CardState(card_id=card.id),
    )
    assert result.net_value_dollars == D("1.00")
    assert any("requires activation" in c for c in result.caveats)


def test_portal_requirement_enforced(wallet):
    """5x via Chase Travel must not pay out on a direct airline booking."""
    card = wallet["chase-sapphire-preferred"]
    direct = evaluate(
        card, Purchase(amount=D("1000"), category="airfare", on=date(2026, 10, 20))
    )
    via_portal = evaluate(
        card,
        Purchase(
            amount=D("1000"),
            category="airfare",
            on=date(2026, 10, 20),
            booked_via_portal="Chase Travel",
        ),
    )
    assert direct.net_value_dollars == D("25.00")       # 2x fallback
    assert via_portal.net_value_dollars == D("62.50")   # 5x
    assert any("only via Chase Travel" in c for c in direct.caveats)


# ---------------------------------------------------------------- fees and edges


def test_foreign_transaction_fee_subtracts(wallet):
    """2.7% FX on $100 costs $2.70 and swamps the 1% base rate."""
    result = evaluate(
        wallet["amex-blue-cash-preferred"],
        Purchase(amount=D("100"), category="other", on=date(2026, 10, 20), is_foreign=True),
    )
    assert result.gross_value_dollars == D("1.00")
    assert result.fees_dollars == D("2.70")
    assert result.net_value_dollars == D("-1.70")
    assert any("foreign transaction fee" in c for c in result.caveats)


def test_no_fx_fee_card_unaffected_abroad(wallet):
    result = evaluate(
        wallet["capital-one-venture-x"],
        Purchase(amount=D("100"), category="other", on=date(2026, 10, 20), is_foreign=True),
    )
    assert result.fees_dollars == D("0")
    assert result.net_value_dollars == D("3.40")  # 2x at 1.7c


def test_insufficient_credit_disqualifies(wallet):
    card = wallet["citi-double-cash"]
    state = CardState(card_id=card.id, available_credit=D("500"))
    result = evaluate(
        card, Purchase(amount=D("3000"), category="other", on=date(2026, 10, 20)), state
    )
    assert result.disqualified
    assert "available credit" in result.disqualified_reason


def test_unknown_credit_is_not_treated_as_zero(wallet):
    card = wallet["citi-double-cash"]
    result = evaluate(
        card,
        Purchase(amount=D("3000"), category="other", on=date(2026, 10, 20)),
        CardState(card_id=card.id, available_credit=None),
    )
    assert not result.disqualified


def test_top_category_card_attaches_caveat(wallet):
    """Custom Cash cannot be settled from one purchase, so it must say so."""
    result = evaluate(
        wallet["citi-custom-cash"],
        Purchase(amount=D("100"), category="dining", on=date(2026, 10, 20)),
    )
    assert result.net_value_dollars == D("5.00")
    assert any("top eligible category" in c for c in result.caveats)


def test_mismatched_state_raises(wallet):
    with pytest.raises(ValueError, match="state is for"):
        evaluate(
            wallet["amex-gold"],
            Purchase(amount=D("10"), category="dining", on=date(2026, 10, 20)),
            CardState(card_id="citi-double-cash"),
        )


def test_unverified_rules_are_reported(wallet):
    """Every seed rule is unverified; the engine must surface that."""
    result = evaluate(
        wallet["amex-gold"],
        Purchase(amount=D("100"), category="dining", on=date(2026, 10, 20)),
    )
    assert result.unverified_rules == ("amex-gold-dining",)


def test_all_category_rule_can_be_gated(wallet):
    """Apple Card's 2% covers every category but requires Apple Pay.

    This is the distinction between "matches any category" and "is the
    unconditional fallback": without Apple Pay the card must drop to 1%, so it
    still needs a real base rate underneath the 2%.
    """
    card = wallet["apple-card"]
    purchase = dict(amount=D("100"), category="superstore", on=date(2026, 10, 20))

    physical = evaluate(card, Purchase(**purchase))
    assert physical.net_value_dollars == D("1.00")
    assert any("only via Apple Pay" in c for c in physical.caveats)

    tapped = evaluate(card, Purchase(**purchase, booked_via_portal="Apple Pay"))
    assert tapped.net_value_dollars == D("2.00")
    assert tapped.components[0].rule_id == "apple-pay-2pct"


def test_gated_all_category_rule_is_not_the_base_rule(wallet):
    """The base rule must be the unconditional one."""
    card = wallet["apple-card"]
    assert card.base_rule.id == "apple-card-base"
