"""PayPal client. Network is mocked -- these assert our handling, not theirs."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from pointwise.paypal import (
    LIVE,
    SANDBOX,
    PayPalClient,
    PayPalConfig,
    PayPalNotConfigured,
    _parse_transaction,
)

D = Decimal
CREDS = PayPalConfig(client_id="id", client_secret="secret")


class TestConfig:
    def test_absent_credentials_are_not_configured(self):
        assert PayPalConfig().configured is False

    def test_both_halves_are_required(self):
        assert PayPalConfig(client_id="id").configured is False
        assert PayPalConfig(client_secret="s").configured is False
        assert CREDS.configured is True

    def test_sandbox_is_the_default_base_url(self):
        assert CREDS.base_url == SANDBOX
        assert PayPalConfig(
            client_id="i", client_secret="s", environment="live"
        ).base_url == LIVE

    def test_from_env_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "abc")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "xyz")
        config = PayPalConfig.from_env()
        assert config.configured
        assert config.client_id == "abc"

    def test_blank_env_vars_count_as_absent(self, monkeypatch):
        """An empty .env line must not look like a credential."""
        monkeypatch.setenv("PAYPAL_CLIENT_ID", "")
        monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "")
        assert PayPalConfig.from_env().configured is False


class TestClientGuards:
    def test_unconfigured_client_raises_a_useful_error(self):
        client = PayPalClient(PayPalConfig())
        assert client.configured is False
        with pytest.raises(PayPalNotConfigured, match="developer.paypal.com"):
            client.access_token()

    def test_transaction_window_is_capped_at_31_days(self):
        client = PayPalClient(CREDS)
        with pytest.raises(ValueError, match="31 days"):
            client.list_transactions(date(2026, 1, 1), date(2026, 3, 1))


class TestTokenCaching:
    def test_token_is_reused_until_it_nears_expiry(self, monkeypatch):
        calls = {"n": 0}

        def fake_post(*args, **kwargs):
            calls["n"] += 1
            return httpx.Response(
                200,
                json={"access_token": f"tok-{calls['n']}", "expires_in": 32400},
                request=httpx.Request("POST", "https://x"),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        client = PayPalClient(CREDS)
        assert client.access_token() == "tok-1"
        assert client.access_token() == "tok-1"
        assert calls["n"] == 1

    def test_expired_token_is_refetched(self, monkeypatch):
        calls = {"n": 0}

        def fake_post(*args, **kwargs):
            calls["n"] += 1
            return httpx.Response(
                200,
                json={"access_token": f"tok-{calls['n']}", "expires_in": 32400},
                request=httpx.Request("POST", "https://x"),
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        client = PayPalClient(CREDS)
        client.access_token()
        client._token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert client.access_token() == "tok-2"
        assert calls["n"] == 2


class TestOrderBody:
    """The vault id is how the engine's choice reaches the funding source."""

    def _capture(self, monkeypatch):
        seen: dict = {}

        def fake_request(method, url, **kwargs):
            seen["method"] = method
            seen["url"] = url
            seen["json"] = kwargs.get("json")
            return httpx.Response(
                200, json={"id": "ORDER-1"}, request=httpx.Request(method, url)
            )

        monkeypatch.setattr(httpx, "request", fake_request)
        monkeypatch.setattr(PayPalClient, "access_token", lambda self: "tok")
        return seen

    def test_order_without_a_vault_id_lets_paypal_choose(self, monkeypatch):
        seen = self._capture(monkeypatch)
        PayPalClient(CREDS).create_order(D("42.50"))
        assert "payment_source" not in seen["json"]
        assert seen["json"]["purchase_units"][0]["amount"]["value"] == "42.50"

    def test_order_with_a_vault_id_pins_the_card(self, monkeypatch):
        seen = self._capture(monkeypatch)
        PayPalClient(CREDS).create_order(D("42.50"), vault_id="VAULT-9")
        assert seen["json"]["payment_source"]["card"]["vault_id"] == "VAULT-9"

    def test_amount_is_always_two_decimal_places(self, monkeypatch):
        seen = self._capture(monkeypatch)
        PayPalClient(CREDS).create_order(D("7"))
        assert seen["json"]["purchase_units"][0]["amount"]["value"] == "7.00"


class TestTransactionParsing:
    def _entry(self, value: str, name: str = "Trader Joe's") -> dict:
        return {
            "transaction_info": {
                "transaction_id": "T-1",
                "transaction_amount": {"value": value, "currency_code": "USD"},
                "transaction_initiation_date": "2026-10-20T12:00:00+0000",
                "transaction_subject": name,
            },
            "payer_info": {},
        }

    def test_debits_are_parsed_as_positive_purchases(self):
        parsed = _parse_transaction(self._entry("-184.22"))
        assert parsed is not None
        assert parsed.amount == D("184.22")
        assert parsed.merchant_name == "Trader Joe's"
        assert parsed.on == date(2026, 10, 20)

    def test_credits_are_skipped(self):
        """A refund is not spend and must not create a phantom missed bonus."""
        assert _parse_transaction(self._entry("25.00")) is None

    def test_entry_without_an_amount_is_skipped(self):
        assert _parse_transaction({"transaction_info": {}}) is None

    def test_unparseable_date_is_skipped(self):
        entry = self._entry("-10.00")
        entry["transaction_info"]["transaction_initiation_date"] = "not-a-date"
        assert _parse_transaction(entry) is None


class TestIdempotency:
    """PayPal requires PayPal-Request-Id with a payment_source.

    It is also the only thing stopping a retried order from charging twice, so
    its presence is asserted rather than assumed.
    """

    def _capture(self, monkeypatch):
        seen: dict = {}

        def fake_request(method, url, **kwargs):
            seen["headers"] = kwargs.get("headers", {})
            seen["json"] = kwargs.get("json")
            return httpx.Response(
                200, json={"id": "ORDER-1"}, request=httpx.Request(method, url)
            )

        monkeypatch.setattr(httpx, "request", fake_request)
        monkeypatch.setattr(PayPalClient, "access_token", lambda self: "tok")
        return seen

    def test_order_with_a_card_sends_a_request_id(self, monkeypatch):
        seen = self._capture(monkeypatch)
        PayPalClient(CREDS).create_order(
            D("10"), card={"number": "4111111111111111", "expiry": "2030-01"}
        )
        assert seen["headers"].get("PayPal-Request-Id", "").startswith("pw-")

    def test_caller_supplied_key_is_preserved_for_safe_retries(self, monkeypatch):
        seen = self._capture(monkeypatch)
        PayPalClient(CREDS).create_order(D("10"), vault_id="V-1", request_id="retry-me")
        assert seen["headers"]["PayPal-Request-Id"] == "retry-me"

    def test_description_is_truncated_to_paypals_limit(self, monkeypatch):
        seen = self._capture(monkeypatch)
        PayPalClient(CREDS).create_order(D("10"), vault_id="V-1", description="x" * 300)
        assert len(seen["json"]["purchase_units"][0]["description"]) == 127
