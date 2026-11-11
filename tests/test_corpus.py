"""Corpus integrity. A malformed rule must fail here, not at a checkout."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from pointwise.categories import Category
from pointwise.loader import audit, load_cards
from pointwise.models import Card, EarnRule, RewardUnit


def test_seed_loads_and_validates():
    cards = load_cards()
    assert len(cards) >= 14


def test_every_rule_category_is_a_known_category():
    """A typo'd category silently never matches, which is the worst failure."""
    valid = {c.value for c in Category}
    for card in load_cards():
        for rule in card.rules:
            unknown = set(rule.categories) - valid
            assert not unknown, f"{rule.id} references unknown categories {unknown}"


def test_every_card_has_exactly_one_catch_all():
    for card in load_cards():
        catch_alls = [r for r in card.rules if r.is_catch_all]
        assert len(catch_alls) == 1, f"{card.id} has {len(catch_alls)} catch-all rules"


def test_card_without_base_rule_is_rejected():
    with pytest.raises(ValidationError, match="catch-all base rule"):
        Card(
            id="broken",
            issuer="Test",
            name="Broken",
            rules=(
                EarnRule(
                    id="only-bonus",
                    label="3% dining",
                    categories=("dining",),
                    rate=Decimal("3"),
                    unit=RewardUnit.CASHBACK_PERCENT,
                ),
            ),
        )


def test_duplicate_rule_ids_rejected():
    base = EarnRule(id="dupe", label="1%", rate=Decimal("1"), unit=RewardUnit.CASHBACK_PERCENT)
    with pytest.raises(ValidationError, match="duplicate rule ids"):
        Card(id="x", issuer="T", name="X", rules=(base, base))


def test_invalid_quarter_rejected():
    with pytest.raises(ValidationError, match="quarters must be 1-4"):
        EarnRule(
            id="bad-q",
            label="5%",
            categories=("grocery",),
            rate=Decimal("5"),
            unit=RewardUnit.CASHBACK_PERCENT,
            active_quarters=(5,),
        )


def test_negative_rate_rejected():
    with pytest.raises(ValidationError):
        EarnRule(id="neg", label="bad", rate=Decimal("-1"), unit=RewardUnit.CASHBACK_PERCENT)


def test_audit_reports_the_review_backlog():
    """The seed ships unverified on purpose; the audit must say so loudly."""
    report = audit(load_cards())
    assert report.total_rules == 40
    assert report.verified_rules == 0
    assert report.unverified_rules == report.total_rules
    assert report.cards_fully_verified == ()
    assert "awaiting review" in report.summary()
