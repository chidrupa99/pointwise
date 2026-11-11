"""The card -> funding source mapping.

The behaviour worth protecting here is the honesty of the fallback: a card can
hold a real vault id and still be charged on a stand-in, and nothing may report
that as a vault-funded purchase.
"""

from __future__ import annotations

import json

import httpx
import pytest

from pointwise import funding
from pointwise.funding import FundingKind, FundingSource
from pointwise.loader import load_cards


@pytest.fixture(scope="module")
def cards():
    return {c.id: c for c in load_cards()}


def _http_error(status: int, name: str = "NOT_AUTHORIZED") -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.invalid/v3/vault/setup-tokens")
    response = httpx.Response(status, json={"name": name}, request=request)
    return httpx.HTTPStatusError(name, request=request, response=response)


class FakeClient:
    """A PayPal client that fails whichever vault tiers the test says to."""

    def __init__(self, v3: bool = True, v1: bool = True, status: int = 403):
        self._v3, self._v1, self._status = v3, v1, status
        self.calls: list[str] = []

    def vault_card(self, card, customer_id=None):
        self.calls.append("v3")
        if not self._v3:
            raise _http_error(self._status)
        return {
            "id": f"TOKEN-{customer_id}",
            "payment_source": {"card": {"brand": "VISA", "last_digits": "1111"}},
        }

    def vault_card_v1(self, card):
        self.calls.append("v1")
        if not self._v1:
            raise _http_error(self._status)
        return {
            "id": f"CARD-{card['external_card_id']}",
            "type": card["type"],
            "number": "xxxxxxxxxxxx" + card["number"][-4:],
        }


class TestNetworkMapping:
    def test_every_seeded_card_maps_to_a_published_test_card(self, cards):
        for card in cards.values():
            key = funding.network_key(card)
            assert key in funding.SANDBOX_TEST_CARDS, card.id

    def test_the_network_matches_the_real_card(self, cards):
        assert funding.network_key(cards["amex-gold"]) == "amex"
        assert funding.network_key(cards["citi-double-cash"]) == "mastercard"
        assert funding.network_key(cards["discover-it"]) == "discover"
        assert funding.network_key(cards["capital-one-venture-x"]) == "visa"

    def test_a_card_with_no_network_still_gets_one(self, cards):
        card = cards["amex-gold"].model_copy(update={"network": None})
        assert funding.network_key(card) == funding.DEFAULT_NETWORK

    def test_amex_gets_a_four_digit_security_code(self, cards):
        amex = funding._inline_card_payload(cards["amex-gold"])
        visa = funding._inline_card_payload(cards["capital-one-venture-x"])
        assert len(amex["security_code"]) == 4
        assert len(visa["security_code"]) == 3


class TestProvisioning:
    def test_v3_is_preferred(self, cards):
        client = FakeClient(v3=True)
        source = funding.provision(client, cards["amex-gold"])
        assert client.calls == ["v3"]
        assert source.kind is FundingKind.VAULT_V3
        assert source.vault_id == "TOKEN-amex-gold"
        assert source.downgrade_reason is None

    def test_falls_back_to_v1_and_says_why(self, cards):
        client = FakeClient(v3=False)
        source = funding.provision(client, cards["amex-gold"])
        assert client.calls == ["v3", "v1"]
        assert source.kind is FundingKind.VAULT_V1
        assert source.vault_id == "CARD-amex-gold"
        assert "NOT_AUTHORIZED" in source.downgrade_reason

    def test_falls_back_to_an_inline_card_when_nothing_vaults(self, cards):
        source = funding.provision(FakeClient(v3=False, v1=False), cards["amex-gold"])
        assert source.kind is FundingKind.SANDBOX_CARD
        assert source.vault_id is None
        assert source.last4 == "0005"  # the Amex test number, not the Visa one

    def test_a_server_error_is_not_swallowed(self, cards):
        """A 500 means PayPal broke, not that we lack permission.

        Degrading on that would hide an outage behind a stand-in card.
        """
        with pytest.raises(httpx.HTTPStatusError):
            funding.provision(FakeClient(v3=False, status=500), cards["amex-gold"])

    def test_each_card_gets_a_distinct_vault_id(self, cards):
        client = FakeClient(v3=False)
        ids = {funding.provision(client, c).vault_id for c in cards.values()}
        assert len(ids) == len(cards)


class TestPaymentSource:
    def test_a_v3_token_is_passed_by_reference(self, cards):
        source = FundingSource(
            card_id="amex-gold", kind=FundingKind.VAULT_V3,
            vault_id="TOKEN-1", network="amex",
        )
        payload = funding.order_payment_source(cards["amex-gold"], source)
        assert payload == {"card": {"vault_id": "TOKEN-1"}}
        assert "number" not in json.dumps(payload)
        assert funding.funded_from_vault(source) is True

    def test_a_v1_id_never_claims_to_fund_the_order(self, cards):
        """The bug this guards: a real vault id that cannot actually pay."""
        source = FundingSource(
            card_id="amex-gold", kind=FundingKind.VAULT_V1,
            vault_id="CARD-1", network="amex",
        )
        payload = funding.order_payment_source(cards["amex-gold"], source)
        assert payload["card"]["number"] == "378282246310005"
        assert funding.funded_from_vault(source) is False

    def test_an_unprovisioned_card_still_charges(self, cards):
        payload = funding.order_payment_source(cards["amex-gold"], None)
        assert payload["card"]["number"]
        assert funding.funded_from_vault(None) is False


class TestRegistryPersistence:
    def test_a_missing_file_reads_as_empty(self, tmp_path):
        assert funding.read(tmp_path / "nope.json") == {}

    def test_round_trip(self, tmp_path):
        path = tmp_path / "funding.json"
        source = FundingSource(
            card_id="amex-gold", kind=FundingKind.VAULT_V1,
            vault_id="CARD-1", network="amex", last4="0005",
        )
        funding.write({"amex-gold": source}, path)
        back = funding.read(path)
        assert back["amex-gold"].vault_id == "CARD-1"
        assert back["amex-gold"].kind is FundingKind.VAULT_V1

    def test_a_corrupt_file_reads_as_empty(self, tmp_path):
        path = tmp_path / "funding.json"
        path.write_text("{ not json")
        assert funding.read(path) == {}

    def test_one_bad_row_does_not_blank_the_rest(self, tmp_path):
        path = tmp_path / "funding.json"
        path.write_text(json.dumps({"sources": [
            {"card_id": "good", "kind": "vault_v1", "network": "visa"},
            {"card_id": "bad", "kind": "not-a-kind", "network": "visa"},
        ]}))
        assert list(funding.read(path)) == ["good"]

    def test_the_write_is_atomic(self, tmp_path):
        path = tmp_path / "funding.json"
        funding.write({"a": FundingSource(
            card_id="a", kind=FundingKind.SANDBOX_CARD, network="visa"
        )}, path)
        assert not list(tmp_path.glob("*.tmp"))
