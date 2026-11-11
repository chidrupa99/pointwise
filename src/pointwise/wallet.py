"""Which cards the user actually holds, and how their welcome offers are going.

Until now the app treated the whole 14-card corpus as the user's wallet, which
made every recommendation a lie of omission: it would tell someone to put a
dinner on an Amex Gold they do not own. The catalog is what exists; the wallet
is what you can actually tap. Only the second may win a recommendation.

The wallet lives on the server rather than on the device because three
different readers need the same answer -- the engine ranking a purchase, the
audit scoring a past one, and the advisor answering a question. A wallet held
only in the app would let the chat and the home screen disagree about what the
user owns, which is the same class of bug as the activity drift.
"""

from __future__ import annotations

import json
import os
import tempfile
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .models import Card, RewardUnit

WALLET_PATH = Path(__file__).resolve().parents[2] / "data" / "wallet.json"

_ZERO = Decimal("0")

#: How long a closed welcome-offer window stays on the card tile. Long
#: enough that a bonus missed last month is still visible and can be
#: learned from; short enough that a wallet built up over years is not a
#: column of dead progress bars.
BONUS_VISIBLE_AFTER_DAYS = 45


class OwnedCard(BaseModel):
    """One card in the user's possession."""

    model_config = ConfigDict(frozen=True)

    card_id: str
    #: When the account was opened. Optional because a user adding a card they
    #: have held for years should not be forced to invent a date -- but without
    #: it there is no welcome-offer window to track, and the app says so rather
    #: than assuming today.
    opened_on: date | None = None
    added_on: date = Field(default_factory=date.today)


class Wallet(BaseModel):
    """Everything the user has told us they hold."""

    model_config = ConfigDict(frozen=True)

    cards: tuple[OwnedCard, ...] = ()

    def holds(self, card_id: str) -> bool:
        return any(c.card_id == card_id for c in self.cards)

    def entry(self, card_id: str) -> OwnedCard | None:
        return next((c for c in self.cards if c.card_id == card_id), None)

    @property
    def is_empty(self) -> bool:
        return not self.cards


class BonusProgress(BaseModel):
    """How a welcome offer is going, in the only terms that matter.

    Every field here answers a question someone actually asks out loud: how
    much more do I have to spend, how long have I got, and have I already
    blown it.
    """

    model_config = ConfigDict(frozen=True)

    points: Decimal
    unit: RewardUnit
    spend_required: Decimal
    spent: Decimal
    remaining: Decimal
    percent: float
    window_ends_on: date
    days_left: int
    earned: bool
    #: True once the window has closed without the spend being met. Kept
    #: distinct from `earned` because "missed it" and "still working on it"
    #: must never render the same way.
    expired: bool


def value_of(bonus_points: Decimal, card: Card) -> Decimal:
    """What a bonus is worth in dollars on this card's own valuation."""
    return (bonus_points * card.point_value_cents / Decimal("100")).quantize(
        Decimal("0.01")
    )


def read(path: Path | str | None = None) -> Wallet:
    """The stored wallet, or an empty one.

    A missing file is a new user, not an error -- that is the empty state the
    app is built to show.
    """
    target = Path(path or WALLET_PATH)
    if not target.exists():
        return Wallet()
    try:
        return Wallet.model_validate(json.loads(target.read_text()))
    except (json.JSONDecodeError, ValueError):
        # A corrupt wallet must not take the app down with it. Better to show
        # the empty state and let the user re-add than to crash on launch.
        return Wallet()


def write(wallet: Wallet, path: Path | str | None = None) -> None:
    """Replace the stored wallet atomically.

    Written to a temporary file and renamed so an interrupted write cannot
    leave a half-written wallet behind -- losing someone's card list to a
    crash mid-save would be an unforgivable way to lose data this small.
    """
    target = Path(path or WALLET_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(wallet.model_dump_json(indent=2))
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def add(card_id: str, opened_on: date | None = None, path=None) -> Wallet:
    """Add a card, or update the open date of one already held."""
    current = read(path)
    kept = tuple(c for c in current.cards if c.card_id != card_id)
    existing = current.entry(card_id)
    entry = OwnedCard(
        card_id=card_id,
        opened_on=opened_on if opened_on is not None else (existing.opened_on if existing else None),
        added_on=existing.added_on if existing else date.today(),
    )
    updated = Wallet(cards=kept + (entry,))
    write(updated, path)
    return updated


def remove(card_id: str, path=None) -> Wallet:
    current = read(path)
    updated = Wallet(cards=tuple(c for c in current.cards if c.card_id != card_id))
    write(updated, path)
    return updated


def owned(catalog: list[Card], wallet: Wallet | None = None) -> list[Card]:
    """The catalog narrowed to what the user holds, in the order they hold it.

    Ignores ids that are not in the catalog rather than raising: a wallet
    written by an older build, or referring to a card since removed from the
    corpus, should degrade to the cards we can still price.
    """
    held = wallet if wallet is not None else read()
    by_id = {c.id: c for c in catalog}
    return [by_id[c.card_id] for c in held.cards if c.card_id in by_id]


def _months_after(start: date, months: int) -> date:
    """The same day-of-month `months` later, clamped to the month's length.

    A card opened on 31 August has a three-month window ending 30 November,
    not an invalid 31 November. `calendar` knows the month lengths and the
    leap years; writing that table out by hand is how off-by-one deadline
    bugs get born.
    """
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def bonus_progress(
    card: Card,
    entry: OwnedCard | None,
    spend_by_card: dict[str, list[tuple[date, Decimal]]],
    today: date | None = None,
) -> BonusProgress | None:
    """Progress toward `card`'s welcome offer, or None if there is nothing to track.

    Returns None when the card has no sourced bonus or the user never told us
    when they opened it. Both are honest absences: a progress bar invented
    from an assumed open date would quietly mislead someone about a deadline
    they cannot afford to miss.
    """
    bonus = card.signup_bonus
    if bonus is None or entry is None or entry.opened_on is None:
        return None

    now = today or date.today()
    ends = _months_after(entry.opened_on, bonus.within_months)
    # A welcome offer stops being news. While the window is open the bar is
    # the most actionable thing on the card, and a window that closed recently
    # still is -- a bonus missed last month is worth knowing about. One that
    # closed two years ago is clutter on a card the user has settled into, and
    # on a wallet built over several years it would put a dead bar on nearly
    # every tile.
    if now > ends + timedelta(days=BONUS_VISIBLE_AFTER_DAYS):
        return None
    # Only spend inside the window counts. Spend from before the account was
    # opened obviously cannot, and the issuer stops counting on the end date.
    spent = sum(
        (amount for on, amount in spend_by_card.get(card.id, []) if entry.opened_on <= on <= ends),
        _ZERO,
    )
    remaining = max(_ZERO, bonus.spend_required - spent)
    earned = spent >= bonus.spend_required
    return BonusProgress(
        points=bonus.points,
        unit=bonus.unit,
        spend_required=bonus.spend_required,
        spent=spent,
        remaining=remaining,
        percent=float(
            min(Decimal("100"), spent / bonus.spend_required * Decimal("100"))
        ),
        window_ends_on=ends,
        days_left=max(0, (ends - now).days),
        earned=earned,
        expired=not earned and now > ends,
    )
