"""Paying with a card the engine did not pick.

The product's whole claim is that it knows the right card, so the interesting
case is the one where the user ignores it. What must not happen is the app
quietly recording its own recommendation instead of what was actually charged:
the activity screen would then show a perfect record and the user would never
learn what their habit costs them.

PayPal is faked here. These tests are about the join between the engine's
ranking and the ledger, and a live capture would make them slow, flaky, and
dependent on someone else's sandbox being up.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pointwise import ledger, routes_money
from pointwise.api import app

D = Decimal


class FakePayPal:
    """Accepts anything and reports a completed capture."""

    configured = True

    def __init__(self):
        self.orders = []

    def create_order(self, amount, currency, payment_source=None, description=""):
        self.orders.append(
            {
                "amount": amount,
                "currency": currency,
                "payment_source": payment_source,
                "description": description,
            }
        )
        return {
            "id": f"ORDER-{len(self.orders)}",
            "status": "COMPLETED",
            "purchase_units": [
                {"payments": {"captures": [{"id": f"CAPTURE-{len(self.orders)}"}]}}
            ],
        }


@pytest.fixture
def paid(monkeypatch):
    """A client whose purchases go nowhere near PayPal or the real ledger."""
    fake = FakePayPal()
    written: list[ledger.LedgerEntry] = []
    monkeypatch.setattr(routes_money, "PAYPAL", fake)
    monkeypatch.setattr(ledger, "append", written.append)
    monkeypatch.setattr(routes_money.ledger, "append", written.append)
    return TestClient(app), fake, written


def buy(client, merchant, amount, card_id=None):
    body = {"merchant": merchant, "amount": str(amount)}
    if card_id:
        body["card_id"] = card_id
    return client.post("/api/checkout", json=body)


class TestTheEngineIsTheDefault:
    def test_without_an_override_the_recommendation_is_charged(self, paid):
        client, _fake, written = paid
        body = buy(client, "Trader Joe's", "120").json()

        assert body["charged_card"]["card_id"] == "amex-gold"
        assert body["followed_recommendation"] is True
        assert D(body["forgone_dollars"]) == 0
        assert written[0].card_id == "amex-gold"

    def test_the_forgone_figure_is_present_even_at_zero(self, paid):
        """A client must not have to read meaning into a missing field."""
        client, _fake, _written = paid
        body = buy(client, "Trader Joe's", "120").json()
        assert "forgone_dollars" in body
        assert "recommended_card_name" in body


class TestAnOverrideIsHonoured:
    def test_the_named_card_is_the_one_charged(self, paid):
        client, _fake, written = paid
        body = buy(client, "Whole Foods", "128.40", "citi-double-cash").json()

        assert body["charged_card"]["card_id"] == "citi-double-cash"
        assert body["followed_recommendation"] is False
        assert body["recommended_card_name"] == "Amex Gold"
        assert D(body["forgone_dollars"]) > 0
        # The crux: the ledger holds what was charged, not what was advised.
        assert written[0].card_id == "citi-double-cash"

    def test_the_forgone_figure_is_the_gap_to_the_best_card(self, paid):
        client, _fake, _written = paid
        rec = client.post(
            "/api/recommend", json={"merchant": "Whole Foods", "amount": "128.40"}
        ).json()
        best = D(rec["ranked"][0]["net_value_dollars"])
        used = next(
            D(e["net_value_dollars"])
            for e in rec["ranked"]
            if e["card_id"] == "citi-double-cash"
        )

        body = buy(client, "Whole Foods", "128.40", "citi-double-cash").json()
        assert D(body["forgone_dollars"]) == best - used

    def test_overriding_to_the_best_card_is_not_a_miss(self, paid):
        """Naming the card the engine would have picked is not an override."""
        client, _fake, _written = paid
        body = buy(client, "Trader Joe's", "120", "amex-gold").json()
        assert body["followed_recommendation"] is True
        assert D(body["forgone_dollars"]) == 0

    def test_the_funding_instrument_follows_the_overridden_card(self, paid):
        """The money must leave the card named, not the recommended one.

        A recommendation that charged a different instrument than it reported
        would be the worst possible bug in this product -- the ledger and the
        bank statement would disagree.
        """
        client, fake, _written = paid
        buy(client, "Whole Foods", "128.40", "citi-double-cash")
        charged = fake.orders[0]["payment_source"]["card"]

        from pointwise import funding
        from pointwise.state import BY_ID

        source = funding.read().get("citi-double-cash")
        expected = funding.order_payment_source(BY_ID["citi-double-cash"], source)
        assert charged == expected["card"]


class TestABadOverrideIsRefused:
    def test_an_unknown_card_id_is_rejected(self, paid):
        client, _fake, written = paid
        response = buy(client, "Trader Joe's", "120", "no-such-card")

        assert response.status_code == 422
        assert "no-such-card" in response.json()["detail"]
        assert written == [], "nothing may be charged for a rejected request"

    def test_a_rejected_override_charges_nothing(self, paid):
        """The refusal must come before PayPal is touched."""
        client, fake, _written = paid
        buy(client, "Trader Joe's", "120", "no-such-card")
        assert fake.orders == []
