"""Loading and auditing the card corpus.

The loader is deliberately strict. A malformed rule should fail at load time,
in a test, rather than surfacing as a wrong dollar figure at a checkout
counter.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .models import Card

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "data" / "cards.seed.json"


class CorpusAudit(BaseModel):
    """Verification state of a loaded corpus, for the review console."""

    model_config = ConfigDict(frozen=True)

    total_cards: int
    total_rules: int
    verified_rules: int
    cards_fully_verified: tuple[str, ...]
    rules_missing_source: tuple[str, ...]

    @property
    def unverified_rules(self) -> int:
        return self.total_rules - self.verified_rules

    @property
    def percent_verified(self) -> float:
        if not self.total_rules:
            return 0.0
        return round(self.verified_rules / self.total_rules * 100, 1)

    def summary(self) -> str:
        return (
            f"{self.total_cards} cards, {self.total_rules} rules, "
            f"{self.verified_rules} verified ({self.percent_verified}%), "
            f"{self.unverified_rules} awaiting review"
        )


def load_cards(path: Path | str | None = None) -> list[Card]:
    """Load and validate the card corpus."""
    source = Path(path) if path else DEFAULT_SEED
    raw = json.loads(source.read_text())
    return [Card.model_validate(entry) for entry in raw["cards"]]


def audit(cards: list[Card]) -> CorpusAudit:
    """Report what still needs a human to sign off on it."""
    rules = [(c, r) for c in cards for r in c.rules]
    return CorpusAudit(
        total_cards=len(cards),
        total_rules=len(rules),
        verified_rules=sum(
            1 for _, r in rules if r.provenance.verified_by_human
        ),
        cards_fully_verified=tuple(c.id for c in cards if c.fully_verified),
        rules_missing_source=tuple(
            r.id for _, r in rules if not r.provenance.source_url
        ),
    )
