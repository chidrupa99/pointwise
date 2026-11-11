"""What `create_sandbox_item` puts on the wire.

Separate from test_plaid.py, which is about the join between a Plaid account
and one of the user's cards. This file is narrower: the exact request shape,
because both fields tested here fail silently when wrong. A missing history
window returns a short feed, and a missing override returns Plaid's stock test
data -- five merchants repeated monthly, twelve rows at exactly $500. Either
one looks like a working integration until you read the numbers.
"""

from __future__ import annotations

import json

import pytest

from pointwise.plaid import PlaidClient, PlaidConfig, PlaidNotConfigured

class TestSandboxRequestShape:
    """What `create_sandbox_item` actually puts on the wire.

    Both of these were found by pointing the code at the real sandbox. The
    history window silently truncated a two-month statement to the last thirty
    days, and the custom-user config has to travel in the one field Plaid
    reserves for it. Neither failure announces itself: you get a short feed, or
    the stock test data, and both look like a working integration.
    """

    @staticmethod
    def _sent(monkeypatch, **kwargs) -> dict:
        client = PlaidClient(PlaidConfig(client_id="id", secret="sec"))
        captured: dict = {}

        def fake_post(path, payload):
            captured["path"] = path
            captured["payload"] = payload
            return {"public_token": "public-sandbox-xyz"}

        monkeypatch.setattr(client, "_post", fake_post)
        client.create_sandbox_item(**kwargs)
        return captured["payload"]

    def test_history_window_is_always_explicit(self, monkeypatch):
        # Plaid documents a 90-day default, but an item created without this
        # came back holding 30. It cannot be changed after creation.
        payload = self._sent(monkeypatch)
        assert payload["options"]["transactions"]["days_requested"] >= 90

    def test_a_custom_user_rides_in_the_password_field(self, monkeypatch):
        config = {"override_accounts": [{"type": "credit"}]}
        payload = self._sent(monkeypatch, custom_user=config)
        options = payload["options"]
        assert options["override_username"] == "user_custom"
        assert json.loads(options["override_password"]) == config

    def test_no_custom_user_means_no_override(self, monkeypatch):
        # Without this the stock institution would be silently overridden by
        # an empty config, which is not the same thing as not asking.
        options = self._sent(monkeypatch)["options"]
        assert "override_username" not in options
        assert "override_password" not in options

    def test_a_custom_user_is_refused_outside_sandbox(self, monkeypatch):
        client = PlaidClient(PlaidConfig(client_id="id", secret="s", environment="production"))
        with pytest.raises(PlaidNotConfigured):
            client.create_sandbox_item(custom_user={"override_accounts": []})
