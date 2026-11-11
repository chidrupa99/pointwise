"""The deterministic reward evaluator.

The model writes the rules; this computes the math. Nothing in this module
calls out to anything -- given a card, a purchase and the user's state, the
result is reproducible and testable.

The non-obvious behaviour is cap splitting: when a purchase crosses a bonus
cap, the portion under the cap earns the bonus rate and the remainder falls to
the base rate. A single blended number is wrong, and this is the single most
common way a rewards calculation goes astray.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .models import (
    CapBasis,
    Card,
    CardEvaluation,
    CardState,
    EarnRule,
    Purchase,
    RewardComponent,
    RewardUnit,
)

CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def _money(value: Decimal) -> Decimal:
    """Round to cents, half-up, the way a statement does."""
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _quarter(month: int) -> int:
    return (month - 1) // 3 + 1


def value_of(rule: EarnRule, spend: Decimal, card: Card) -> tuple[Decimal, Decimal]:
    """Return (reward_quantity, value_dollars) for `spend` under `rule`."""
    if rule.unit is RewardUnit.CASHBACK_PERCENT:
        dollars = spend * rule.rate / Decimal("100")
        return dollars, dollars
    points = spend * rule.rate
    return points, points * card.point_value_cents / Decimal("100")


def _rule_is_eligible(
    rule: EarnRule, purchase: Purchase, state: CardState
) -> tuple[bool, str | None]:
    """Decide whether a rule can apply at all. Returns (eligible, why_not)."""
    if rule.categories and purchase.category not in rule.categories:
        return False, None  # simply doesn't match; not worth reporting

    if rule.active_quarters is not None:
        q = _quarter(purchase.on.month)
        if q not in rule.active_quarters:
            return False, f"{rule.label}: not active in Q{q}"

    if rule.requires_activation and rule.id not in state.activated_rule_ids:
        return False, f"{rule.label}: requires activation and is not activated"

    if rule.requires_portal and purchase.booked_via_portal != rule.requires_portal:
        return False, f"{rule.label}: only via {rule.requires_portal}"

    return True, None


def _capped_spend(rule: EarnRule, spend: Decimal, state: CardState, card: Card) -> Decimal:
    """How much of `spend` can earn at the rule's bonus rate.

    Returns the full amount when there is no cap. A fully consumed cap returns
    zero, which pushes the whole purchase to the base rate.
    """
    if rule.cap is None:
        return spend

    used = state.usage.get(rule.id)
    if used is None:
        return spend

    if rule.cap.basis is CapBasis.SPEND:
        remaining = rule.cap.amount - used.spend_to_date
        return max(_ZERO, min(spend, remaining))

    # Reward-basis cap: invert the rate to find how much spend fits.
    remaining_reward = rule.cap.amount - used.reward_to_date
    if remaining_reward <= _ZERO:
        return _ZERO
    _, value_per_dollar = value_of(rule, Decimal("1"), card)
    if value_per_dollar <= _ZERO:
        return _ZERO
    affordable = remaining_reward / value_per_dollar
    return max(_ZERO, min(spend, affordable))


def _best_bonus_rule(
    card: Card, purchase: Purchase, state: CardState
) -> tuple[EarnRule | None, list[str]]:
    """Pick the highest-value eligible bonus rule, collecting near-misses.

    Ranking is by value per dollar rather than by raw rate, because 3 points on
    a card worth 1.8 cents a point beats 4% cashback and the rate alone does
    not say so.
    """
    caveats: list[str] = []
    best: EarnRule | None = None
    best_value = _ZERO

    for rule in card.rules:
        if rule.is_catch_all:
            continue
        eligible, why_not = _rule_is_eligible(rule, purchase, state)
        if not eligible:
            if why_not:
                caveats.append(why_not)
            continue
        _, value_per_dollar = value_of(rule, Decimal("1"), card)
        if value_per_dollar > best_value:
            best, best_value = rule, value_per_dollar

    return best, caveats


def evaluate(card: Card, purchase: Purchase, state: CardState | None = None) -> CardEvaluation:
    """Score one purchase on one card.

    The returned components show the full working: which rule applied to which
    slice of the purchase and what each slice earned.
    """
    if state is None:
        state = CardState(card_id=card.id)
    if state.card_id != card.id:
        raise ValueError(f"state is for {state.card_id!r}, not {card.id!r}")

    components: list[RewardComponent] = []
    caveats: list[str] = []

    bonus_rule, near_misses = _best_bonus_rule(card, purchase, state)
    caveats.extend(near_misses)

    remaining = purchase.amount

    if bonus_rule is not None:
        bonus_spend = _capped_spend(bonus_rule, remaining, state, card)
        if bonus_spend > _ZERO:
            qty, value = value_of(bonus_rule, bonus_spend, card)
            components.append(
                RewardComponent(
                    rule_id=bonus_rule.id,
                    rule_label=bonus_rule.label,
                    spend_applied=_money(bonus_spend),
                    rate=bonus_rule.rate,
                    unit=bonus_rule.unit,
                    reward_quantity=qty,
                    value_dollars=_money(value),
                    reason=f"matched {purchase.category}",
                )
            )
            remaining -= bonus_spend

        if bonus_rule.cap is not None and bonus_spend < purchase.amount:
            spent_over = purchase.amount - bonus_spend
            caveats.append(
                f"{bonus_rule.label}: cap reached ({bonus_rule.cap.label}); "
                f"${spent_over:,.2f} of this purchase earns the base rate"
            )

    # Whatever the bonus didn't absorb falls to the base rate.
    if remaining > _ZERO:
        base = card.base_rule
        qty, value = value_of(base, remaining, card)
        reason = "base rate" if bonus_rule is None else "above bonus cap"
        components.append(
            RewardComponent(
                rule_id=base.id,
                rule_label=base.label,
                spend_applied=_money(remaining),
                rate=base.rate,
                unit=base.unit,
                reward_quantity=qty,
                value_dollars=_money(value),
                reason=reason,
            )
        )

    gross = sum((c.value_dollars for c in components), _ZERO)

    fees = _ZERO
    if purchase.is_foreign and card.foreign_transaction_fee_percent > _ZERO:
        fees = _money(
            purchase.amount * card.foreign_transaction_fee_percent / Decimal("100")
        )
        caveats.append(
            f"{card.foreign_transaction_fee_percent}% foreign transaction fee "
            f"costs ${fees:,.2f}"
        )

    if card.bonus_limited_to_top_category and bonus_rule is not None:
        caveats.append(
            "Bonus applies only to your top eligible category for the cycle; "
            "this assumes it is that category"
        )

    disqualified = False
    reason: str | None = None
    if state.available_credit is not None and purchase.amount > state.available_credit:
        disqualified = True
        reason = (
            f"available credit ${state.available_credit:,.2f} is below the "
            f"${purchase.amount:,.2f} purchase"
        )

    net = _money(gross - fees)
    effective = (
        (net / purchase.amount * Decimal("100")).quantize(CENTS, rounding=ROUND_HALF_UP)
        if purchase.amount > _ZERO
        else _ZERO
    )

    return CardEvaluation(
        card_id=card.id,
        card_name=card.name,
        components=tuple(components),
        gross_value_dollars=_money(gross),
        fees_dollars=fees,
        net_value_dollars=net,
        effective_rate_percent=effective,
        caveats=tuple(caveats),
        disqualified=disqualified,
        disqualified_reason=reason,
        unverified_rules=tuple(
            c.rule_id
            for c in components
            if not next(
                r for r in card.rules if r.id == c.rule_id
            ).provenance.verified_by_human
        ),
    )
