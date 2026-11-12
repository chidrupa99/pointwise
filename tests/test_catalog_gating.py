"""Which cards the picker lets you add.

The rule exists to stop someone adding a card the app already knows is not
there. An issuer whose connection returned two accounts, both claimed, cannot
be hiding a third -- a tile for it would sit at zero forever with nothing the
user could do about it.
"""

from __future__ import annotations

from pointwise.routes_money import _blocked_reason
from pointwise.state import BY_ID

GOLD = BY_ID["amex-gold"]
PLATINUM = BY_ID["amex-platinum"]
SAPPHIRE = BY_ID["chase-sapphire-preferred"]


class TestBlockedReason:
    def test_an_unconnected_issuer_blocks_nothing(self):
        """Without a connection we know nothing, so the user may assert it."""
        assert _blocked_reason(SAPPHIRE, False, set(), set()) is None

    def test_a_claimed_connection_blocks_its_other_cards(self):
        reason = _blocked_reason(PLATINUM, False, {"American Express"}, set())
        assert reason == "Not on your American Express connection"

    def test_a_spare_account_leaves_it_open(self):
        """An unclaimed account could still turn out to be this card."""
        assert (
            _blocked_reason(
                PLATINUM, False, {"American Express"}, {"American Express"}
            )
            is None
        )

    def test_a_held_card_is_never_blocked(self):
        """Otherwise the checkbox that added it could not take it away."""
        assert _blocked_reason(PLATINUM, True, {"American Express"}, set()) is None

    def test_another_issuer_is_unaffected(self):
        assert _blocked_reason(SAPPHIRE, False, {"American Express"}, set()) is None
