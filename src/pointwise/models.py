"""The reward rules schema.

This is the contract between the extraction pipeline and the engine: the model
reads cardmember agreements and emits these structures, a human reviews them,
and the engine evaluates them deterministically. Nothing here is computed by
an LLM at request time.

Money is Decimal throughout. Floats are not permitted anywhere a dollar or a
rate is represented.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Period(str, Enum):
    """The window a cap resets on."""

    MONTH = "month"
    BILLING_CYCLE = "billing_cycle"
    CALENDAR_QUARTER = "calendar_quarter"
    CALENDAR_YEAR = "calendar_year"
    ANNIVERSARY_YEAR = "anniversary_year"
    LIFETIME = "lifetime"


class RewardUnit(str, Enum):
    """What a rule pays out in.

    CASHBACK_PERCENT: rate 4 means 4% back, worth 4 cents per dollar.
    POINTS / MILES:   rate 4 means 4 points per dollar, valued by the card's
                      point_value_cents.
    """

    CASHBACK_PERCENT = "cashback_percent"
    POINTS = "points"
    MILES = "miles"


class CapBasis(str, Enum):
    """Whether a cap limits qualifying spend or the reward paid out."""

    SPEND = "spend"
    REWARD = "reward"


class Provenance(BaseModel):
    """Where a rule came from, so a human can check it.

    Required on every rule. An unsourced rule is not reviewable, and an
    unreviewed rule should never reach a user-facing dollar figure.
    """

    model_config = ConfigDict(frozen=True)

    source_url: str | None = None
    quote: str | None = Field(
        default=None, description="Verbatim text the rule was extracted from."
    )
    extracted_on: date | None = None
    verified_by_human: bool = False


class SignupBonus(BaseModel):
    """The welcome offer: spend this much within this long, get these points.

    Modelled apart from EarnRule because it behaves nothing like a rate. It
    pays once, it expires, and falling a dollar or a day short pays exactly
    nothing -- which makes it the highest-stakes number in the app. A user who
    mistimes a 60,000-point offer loses more than a year of category bonuses
    would earn them, and no rate comparison anywhere else in this product
    comes close to mattering that much.
    """

    model_config = ConfigDict(frozen=True)

    points: Decimal = Field(gt=0)
    spend_required: Decimal = Field(gt=0)
    within_months: int = Field(gt=0, le=24)
    unit: RewardUnit = RewardUnit.POINTS
    provenance: Provenance = Provenance()


class Cap(BaseModel):
    """A ceiling on a bonus rate, after which spend falls to the base rate."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(gt=0)
    basis: CapBasis = CapBasis.SPEND
    period: Period = Period.CALENDAR_YEAR

    @property
    def label(self) -> str:
        unit = "spend" if self.basis is CapBasis.SPEND else "reward"
        return f"${self.amount:,.0f} {unit} per {self.period.value.replace('_', ' ')}"


class EarnRule(BaseModel):
    """One earn rate on one card.

    A rule with an empty `categories` list is a catch-all and matches any
    purchase; that is how base rates are expressed.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    categories: tuple[str, ...] = ()
    rate: Decimal = Field(gt=0)
    unit: RewardUnit
    cap: Cap | None = None

    # Rotating-category machinery
    active_quarters: tuple[int, ...] | None = Field(
        default=None,
        description="Calendar quarters (1-4) this rule is live. None = always.",
    )
    requires_activation: bool = False

    # Channel restrictions
    requires_portal: str | None = Field(
        default=None,
        description="Booking channel required, e.g. 'Chase Travel'. None = anywhere.",
    )

    provenance: Provenance = Provenance()
    notes: str | None = None

    @model_validator(mode="after")
    def _check_quarters(self) -> EarnRule:
        if self.active_quarters is not None:
            if not self.active_quarters:
                raise ValueError(f"{self.id}: active_quarters cannot be empty")
            bad = [q for q in self.active_quarters if q not in (1, 2, 3, 4)]
            if bad:
                raise ValueError(f"{self.id}: quarters must be 1-4, got {bad}")
        return self

    @property
    def matches_any_category(self) -> bool:
        """An empty category list means the rule applies to all spend."""
        return not self.categories

    @property
    def is_gated(self) -> bool:
        """True when the rule only applies under some condition."""
        return (
            self.active_quarters is not None
            or self.requires_activation
            or self.requires_portal is not None
        )

    @property
    def is_catch_all(self) -> bool:
        """The unconditional fallback rate.

        A rule covering every category but gated on a channel -- Apple Card's
        2% via Apple Pay, or a mobile-wallet bonus -- is NOT the fallback. It
        is an all-category bonus that can fail to apply, so the card still
        needs a true base rate underneath it.
        """
        return self.matches_any_category and not self.is_gated


class Card(BaseModel):
    """A card and everything needed to score a purchase on it."""

    model_config = ConfigDict(frozen=True)

    id: str
    issuer: str
    name: str
    network: str | None = None

    annual_fee: Decimal = Decimal("0")
    foreign_transaction_fee_percent: Decimal = Decimal("0")

    point_value_cents: Decimal = Field(
        default=Decimal("1.0"),
        gt=0,
        description=(
            "Default cents-per-point. A transferable currency redeemed well is "
            "worth more than one redeemed for statement credit, so this is a "
            "per-user assumption, not a property of the card."
        ),
    )

    rules: tuple[EarnRule, ...]

    #: The welcome offer, when the card has one worth tracking. Absent rather
    #: than zeroed when unknown: a bonus we have not sourced must not render as
    #: a progress bar reading 0 of 0.
    signup_bonus: SignupBonus | None = None

    #: Set when the bonus applies only to the cardholder's top spend category
    #: for the period (Citi Custom Cash and similar). The engine cannot settle
    #: this from a single purchase, so it attaches a caveat instead of guessing.
    bonus_limited_to_top_category: bool = False

    @model_validator(mode="after")
    def _check_rules(self) -> Card:
        if not self.rules:
            raise ValueError(f"{self.id}: card must have at least one rule")
        if not any(r.is_catch_all for r in self.rules):
            raise ValueError(
                f"{self.id}: card must have a catch-all base rule "
                "(an EarnRule with no categories)"
            )
        ids = [r.id for r in self.rules]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"{self.id}: duplicate rule ids {sorted(dupes)}")
        return self

    @property
    def base_rule(self) -> EarnRule:
        """The catch-all. Guaranteed to exist by the validator."""
        return next(r for r in self.rules if r.is_catch_all)

    @property
    def fully_verified(self) -> bool:
        return all(r.provenance.verified_by_human for r in self.rules)


class Purchase(BaseModel):
    """A purchase being scored."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(gt=0)
    category: str
    on: date
    merchant_name: str | None = None
    mcc: str | None = None
    is_foreign: bool = False
    booked_via_portal: str | None = Field(
        default=None, description="Channel the purchase is being made through."
    )


class CapUsage(BaseModel):
    """How much of one rule's cap is already consumed in the current period."""

    model_config = ConfigDict(frozen=True)

    spend_to_date: Decimal = Decimal("0")
    reward_to_date: Decimal = Decimal("0")


class CardState(BaseModel):
    """Per-user, per-card state the engine needs but cannot derive.

    All of it is optional: absent state means an unconstrained card, which is
    the right default for a first-run user who has entered nothing.
    """

    model_config = ConfigDict(frozen=True)

    card_id: str
    #: rule_id -> usage within the rule's current cap period.
    usage: dict[str, CapUsage] = Field(default_factory=dict)
    #: Rule ids the user has activated, for rules that require it.
    activated_rule_ids: frozenset[str] = frozenset()
    #: From an aggregator. None means unknown, which must not be read as zero.
    available_credit: Decimal | None = None
    #: Drives ANNIVERSARY_YEAR cap periods.
    opened_on: date | None = None


class RewardComponent(BaseModel):
    """One slice of a purchase earning at one rate.

    A purchase that crosses a cap produces several of these -- which is the
    whole reason the math lives in code.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str
    rule_label: str
    spend_applied: Decimal
    rate: Decimal
    unit: RewardUnit
    reward_quantity: Decimal
    value_dollars: Decimal
    reason: str


class CardEvaluation(BaseModel):
    """What a card would earn on a purchase, and why."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    card_name: str
    components: tuple[RewardComponent, ...]
    gross_value_dollars: Decimal
    fees_dollars: Decimal
    net_value_dollars: Decimal
    effective_rate_percent: Decimal
    caveats: tuple[str, ...] = ()
    disqualified: bool = False
    disqualified_reason: str | None = None
    unverified_rules: tuple[str, ...] = ()
