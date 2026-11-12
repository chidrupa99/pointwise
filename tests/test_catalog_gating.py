"""What the picker knows about a card the connection does not carry.

The fact and the consequence are deliberately separate. An issuer whose
connection returned accounts that are all claimed cannot be hiding another
card -- that is true whether or not the user already holds it. What holding
it changes is only whether the row can still be ticked off, so that a card
added by mistake can be taken out again.
"""

from __future__ import annotations

from pointwise.routes_money import _absent_from_connection
from pointwise.state import BY_ID

GOLD = BY_ID["amex-gold"]
PLATINUM = BY_ID["amex-platinum"]
SAPPHIRE = BY_ID["chase-sapphire-preferred"]

AMEX = {"American Express"}


class TestAbsentFromConnection:
    def test_an_unconnected_issuer_tells_us_nothing(self):
        """Without a connection there is no absence to report."""
        assert _absent_from_connection(SAPPHIRE, set(), set(), set()) is False

    def test_a_fully_claimed_connection_means_absent(self):
        assert _absent_from_connection(PLATINUM, {"amex-gold"}, AMEX, set()) is True

    def test_a_spare_account_leaves_it_open(self):
        """An unclaimed account could still turn out to be this card."""
        assert _absent_from_connection(PLATINUM, {"amex-gold"}, AMEX, AMEX) is False

    def test_a_card_being_read_is_present_by_definition(self):
        assert _absent_from_connection(GOLD, {"amex-gold"}, AMEX, set()) is False

    def test_another_issuer_is_unaffected(self):
        assert _absent_from_connection(SAPPHIRE, {"amex-gold"}, AMEX, set()) is False

    def test_holding_the_card_does_not_change_the_fact(self):
        """Held or not, the connection either carries it or it does not.

        The picker shows the same note either way and only withholds the tick
        from a card that is not already in the wallet.
        """
        absent = _absent_from_connection(PLATINUM, {"amex-gold"}, AMEX, set())
        assert absent is True
