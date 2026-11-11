"""Sign-in.

Two things matter here and neither is the happy path. First, the app must say
honestly whether PayPal login is actually available, because the alternative is
a button that always fails. Second, a local sign-in must never claim to be a
PayPal one -- the whole point of showing the method in the UI is that the
difference is real.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from pointwise import auth
from pointwise.api import app
from pointwise.auth import AuthNotAvailable, Profile
from pointwise.paypal import PayPalConfig


@pytest.fixture(autouse=True)
def _own_profile_file(tmp_path, monkeypatch):
    """Never read or write the developer's real profile."""
    monkeypatch.setattr(auth, "PROFILE_PATH", tmp_path / "profile.json")


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "PAYPAL_LOGIN_REDIRECT_URI", "https://example.test/auth/paypal/callback"
    )


class TestAvailability:
    def test_without_a_client_id_it_is_unavailable(self, monkeypatch):
        monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
        monkeypatch.delenv("PAYPAL_LOGIN_REDIRECT_URI", raising=False)
        ok, why = auth.login_available(PayPalConfig(client_id=None))
        assert ok is False
        assert "PAYPAL_CLIENT_ID" in why

    def test_without_a_return_url_it_is_unavailable(self, monkeypatch):
        """This is the real-world case: credentials exist, the URL does not.

        PayPal rejects the authorize request outright without a registered
        return URL, so offering the button would be offering a dead end.
        """
        monkeypatch.delenv("PAYPAL_LOGIN_REDIRECT_URI", raising=False)
        ok, why = auth.login_available(PayPalConfig(client_id="x", client_secret="y"))
        assert ok is False
        assert "return URL" in why

    def test_fully_configured_is_available(self, configured):
        ok, why = auth.login_available()
        assert ok is True
        assert why is None

    def test_starting_the_flow_without_config_raises(self, monkeypatch):
        monkeypatch.delenv("PAYPAL_LOGIN_REDIRECT_URI", raising=False)
        with pytest.raises(AuthNotAvailable):
            auth.authorize_url("state", PayPalConfig(client_id="x", client_secret="y"))


class TestAuthorizeUrl:
    def test_it_is_a_well_formed_oidc_request(self, configured):
        url = auth.authorize_url("abc123")
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        assert parsed.netloc == "www.sandbox.paypal.com"
        assert query["response_type"] == ["code"]
        assert query["client_id"] == ["test-client-id"]
        assert query["state"] == ["abc123"]
        assert query["redirect_uri"] == ["https://example.test/auth/paypal/callback"]

    def test_it_asks_for_nothing_beyond_a_name(self, configured):
        """Scope creep on a consent screen is how a sign-in starts looking
        alarming. The app needs an identity and a name, nothing else."""
        scopes = set(parse_qs(urlparse(auth.authorize_url("s")).query)["scope"][0].split())
        assert scopes == {"openid", "profile", "email"}

    def test_live_environment_uses_the_live_host(self, configured, monkeypatch):
        monkeypatch.setenv("PAYPAL_ENV", "live")
        url = auth.authorize_url("s", PayPalConfig.from_env())
        assert urlparse(url).netloc == "www.paypal.com"

    def test_each_state_is_unique(self):
        assert len({auth.new_state() for _ in range(50)}) == 50


class TestProfileStore:
    def test_nobody_signed_in_reads_as_none(self):
        assert auth.read() is None

    def test_round_trip(self):
        auth.write(Profile(name="Ada", email="ada@example.test", method="paypal"))
        got = auth.read()
        assert got.name == "Ada"
        assert got.verified is True

    def test_a_corrupt_profile_reads_as_signed_out(self):
        auth.PROFILE_PATH.write_text("not json")
        assert auth.read() is None

    def test_sign_out_forgets_the_profile(self):
        auth.write(Profile(name="Ada"))
        auth.sign_out()
        assert auth.read() is None

    def test_sign_out_is_idempotent(self):
        auth.sign_out()
        auth.sign_out()


class TestTheEndpoints:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_status_reports_signed_out(self, client, monkeypatch):
        monkeypatch.delenv("PAYPAL_LOGIN_REDIRECT_URI", raising=False)
        body = client.get("/api/auth/status").json()
        assert body["signed_in"] is False
        assert body["profile"] is None
        assert body["paypal_login_available"] is False
        assert body["paypal_login_hint"]

    def test_start_is_503_when_unavailable(self, client, monkeypatch):
        """Not a 500. The flow is unconfigured, which is a known state the app
        is built to handle, not a server fault."""
        monkeypatch.delenv("PAYPAL_LOGIN_REDIRECT_URI", raising=False)
        assert client.post("/api/auth/paypal/start").status_code == 503

    def test_start_hands_back_a_url(self, client, configured):
        body = client.post("/api/auth/paypal/start").json()
        assert body["url"].startswith("https://www.sandbox.paypal.com/signin/authorize")
        assert body["state"] in body["url"]

    def test_local_sign_in_is_never_marked_verified(self, client):
        """The one claim this path must not make."""
        body = client.post("/api/auth/local", json={"name": "Ada"}).json()
        assert body["profile"]["method"] == "local"
        assert body["profile"]["verified"] is False

    def test_local_sign_in_requires_a_name(self, client):
        assert client.post("/api/auth/local", json={"name": ""}).status_code == 422
        assert client.post("/api/auth/local", json={}).status_code == 422

    def test_signing_in_then_out(self, client):
        client.post("/api/auth/local", json={"name": "Ada"})
        assert client.get("/api/auth/status").json()["signed_in"] is True
        client.post("/api/auth/signout")
        assert client.get("/api/auth/status").json()["signed_in"] is False

    def test_the_callback_refuses_an_unknown_state(self, client):
        """A code we did not ask for is never exchanged."""
        response = client.get(
            "/auth/paypal/callback", params={"code": "abc", "state": "never-issued"}
        )
        assert response.status_code == 400
        assert "expired" in response.text.lower()

    def test_the_callback_reports_paypals_own_error(self, client):
        response = client.get("/auth/paypal/callback", params={"error": "access_denied"})
        assert response.status_code == 400
        assert "access_denied" in response.text

    def test_a_used_state_cannot_be_replayed(self, client, configured, monkeypatch):
        state = client.post("/api/auth/paypal/start").json()["state"]

        def fake_exchange(code, config=None):
            return {"access_token": "tok"}

        def fake_profile(token, config=None):
            return Profile(
                name="Ada",
                method="paypal",
                signed_in_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )

        monkeypatch.setattr(auth, "exchange_code", fake_exchange)
        monkeypatch.setattr(auth, "fetch_profile", fake_profile)

        first = client.get("/auth/paypal/callback", params={"code": "c", "state": state})
        assert first.status_code == 200
        second = client.get("/auth/paypal/callback", params={"code": "c", "state": state})
        assert second.status_code == 400

    def test_the_wallet_survives_signing_out(self, client):
        """Losing the cards you entered because you signed out of a demo would
        be a hostile surprise, and none of it is secret."""
        from pointwise import wallet

        wallet.add("amex-gold")
        client.post("/api/auth/local", json={"name": "Ada"})
        client.post("/api/auth/signout")
        assert wallet.read().holds("amex-gold")
