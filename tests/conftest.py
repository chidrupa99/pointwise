"""Test isolation.

Once real credentials sit in .env, `load_dotenv` puts them in the environment
at import time and the API's module-level client becomes live -- which would
make the suite hit PayPal's network, turning fast local tests into slow flaky
ones that depend on someone else's uptime.

Clearing the variables for the whole session keeps tests hermetic. Anything
that needs credentials sets them explicitly with monkeypatch.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_real_paypal_credentials() -> None:
    import os

    for key in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_ENV"):
        os.environ.pop(key, None)


@pytest.fixture(autouse=True)
def _wallet_is_not_the_users(tmp_path, monkeypatch) -> None:
    """Keep the suite off the real wallet file, in both directions.

    Reading it would make test outcomes depend on whichever cards the developer
    happens to hold, and `wallet.add` writes -- so a careless test could edit
    someone's actual card list. Each test gets its own empty wallet file.

    The default wallet is the whole catalog, which is what every engine and API
    test written before the wallet existed assumes. Tests about the wallet
    itself set their own.

    Each module that needs the wallet imported `my_cards` by name, so patching
    it on `state` alone leaves those bindings pointing at the original. Every
    binding is replaced here, including the one the advisor captured when it
    was constructed at import time.
    """
    from pointwise import api, routes_money, state, wallet

    def whole_catalog():
        return state.CATALOG

    monkeypatch.setattr(wallet, "WALLET_PATH", tmp_path / "wallet.json")
    # Same reasoning for the linked-issuer store: `activity_feed` reads its
    # cache, so without this the suite's results depend on whether the
    # developer happens to have an issuer linked.
    from pointwise import plaid_store

    monkeypatch.setattr(plaid_store, "STORE_PATH", tmp_path / "plaid.json")
    monkeypatch.setattr(plaid_store, "CACHE_PATH", tmp_path / "plaid_txns.json")
    for module in (state, api, routes_money):
        monkeypatch.setattr(module, "my_cards", whole_catalog)
    monkeypatch.setattr(state.ADVISOR, "_cards_source", whole_catalog)
