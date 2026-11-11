"""Linking an issuer and reading its transactions.

Plaid is faked here. These tests are about the join that makes the whole
integration worth building -- a Plaid account id becoming one of the user's
cards -- plus the two things that go quietly wrong with an incremental feed:
losing the cursor, and leaking the access token.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pointwise import plaid_store, routes_plaid
from pointwise.api import app
from pointwise.plaid import PlaidAccount, PlaidConfig, PlaidNotConfigured, PlaidTransaction
from pointwise.plaid_store import CachedTransaction

D = Decimal


@pytest.fixture(autouse=True)
def _own_files(tmp_path, monkeypatch):
    """Never read or write the real link store or transaction cache."""
    monkeypatch.setattr(plaid_store, "STORE_PATH", tmp_path / "plaid.json")
    monkeypatch.setattr(plaid_store, "CACHE_PATH", tmp_path / "plaid_txns.json")


class FakePlaid:
    """Stands in for a linked sandbox issuer."""

    configured = True

    def __init__(self, accounts=None, pages=None):
        self.config = PlaidConfig(
            client_id="test-id", secret="test-secret", environment="sandbox"
        )
        self._accounts = accounts if accounts is not None else [
            PlaidAccount(
                account_id="acct-gold",
                name="Gold Card",
                mask="1009",
                type="credit",
                subtype="credit card",
            ),
            PlaidAccount(
                account_id="acct-checking",
                name="Plaid Checking",
                mask="0000",
                type="depository",
                subtype="checking",
            ),
        ]
        self._pages = pages or [
            {
                "added": [
                    PlaidTransaction(
                        transaction_id="t1",
                        account_id="acct-gold",
                        amount=D("128.40"),
                        on=date(2026, 10, 20),
                        name="SQ *WHOLE FOODS 0423",
                        merchant_name="Whole Foods",
                        category_primary="FOOD_AND_DRINK",
                    )
                ],
                "modified": [],
                "removed": [],
                "next_cursor": "cursor-1",
                "has_more": False,
            }
        ]
        self.sync_calls: list[str | None] = []

    def create_sandbox_item(self, institution_id=None):
        return "public-sandbox-token-abcdef"

    def exchange(self, public_token):
        return {"access_token": "access-sandbox-SECRET", "item_id": "item-1"}

    def accounts(self, access_token):
        return self._accounts

    def sync(self, access_token, cursor=None):
        self.sync_calls.append(cursor)
        return self._pages[min(len(self.sync_calls) - 1, len(self._pages) - 1)]


@pytest.fixture
def linked(monkeypatch):
    fake = FakePlaid()
    monkeypatch.setattr(routes_plaid, "PLAID", fake)
    return TestClient(app), fake


class TestStatus:
    def test_unconfigured_says_so_without_failing(self, monkeypatch):
        """The app must render before anyone has pasted a key."""
        from pointwise.plaid import PlaidClient

        monkeypatch.setattr(
            routes_plaid, "PLAID", PlaidClient(PlaidConfig(client_id=None, secret=None))
        )
        body = TestClient(app).get("/api/plaid/status").json()
        assert body["configured"] is False
        assert body["connected"] is False
        assert "PLAID_CLIENT_ID" in body["hint"]

    def test_linking_without_credentials_is_503(self, monkeypatch):
        from pointwise.plaid import PlaidClient

        monkeypatch.setattr(
            routes_plaid, "PLAID", PlaidClient(PlaidConfig(client_id=None, secret=None))
        )
        assert TestClient(app).post("/api/plaid/sandbox-link").status_code == 503


class TestLinking:
    def test_the_sandbox_shortcut_links_an_item(self, linked):
        client, _fake = linked
        body = client.post("/api/plaid/sandbox-link").json()

        assert body["linked"] is True
        assert body["credit_accounts"] == 1
        assert body["other_accounts"] == 1

    def test_only_credit_cards_are_offered(self, linked):
        """A chequing account cannot win a recommendation."""
        client, _fake = linked
        body = client.post("/api/plaid/sandbox-link").json()
        ids = [a["account_id"] for a in body["link"]["accounts"]]
        assert ids == ["acct-gold"]

    def test_the_access_token_never_leaves_the_server(self, linked):
        """The one thing in this module that must not be on a wire.

        It is a long-lived credential to someone's bank data. Every response
        shape goes through `redacted`, and this asserts that it stays that way.
        """
        client, _fake = linked
        for response in (
            client.post("/api/plaid/sandbox-link"),
            client.get("/api/plaid/status"),
        ):
            assert "access-sandbox-SECRET" not in response.text
            assert "access_token" not in response.json().__repr__().replace(
                "access_token_length", ""
            )

    def test_the_token_is_stored_with_owner_only_permissions(self, linked):
        client, _fake = linked
        client.post("/api/plaid/sandbox-link")
        mode = plaid_store.STORE_PATH.stat().st_mode & 0o777
        assert mode == 0o600, oct(mode)

    def test_a_sandbox_shortcut_is_refused_outside_sandbox(self, monkeypatch):
        fake = FakePlaid()
        monkeypatch.setattr(
            fake, "config", PlaidConfig(client_id="x", secret="y", environment="production")
        )
        monkeypatch.setattr(routes_plaid, "PLAID", fake)
        assert TestClient(app).post("/api/plaid/sandbox-link").status_code == 400


class TestMapping:
    def test_an_unmapped_account_leaves_its_rows_unscored(self, linked):
        """Which is honest: without a card there is no rate to price it with."""
        client, _fake = linked
        client.post("/api/plaid/sandbox-link")
        client.post("/api/plaid/sync")
        rows = plaid_store.read_cache()
        assert rows and all(r.card_id is None for r in rows)

    def test_mapping_reprices_rows_already_synced(self, linked):
        """Mapping happens after the first sync.

        Without the repricing pass the user confirms their cards and the feed
        stubbornly stays unscored, which looks like the app ignoring them.
        """
        client, _fake = linked
        item = client.post("/api/plaid/sandbox-link").json()["link"]["item_id"]
        client.post("/api/plaid/sync")

        client.post(
            "/api/plaid/map",
            json={"item_id": item, "account_id": "acct-gold", "card_id": "amex-gold"},
        )
        assert all(r.card_id == "amex-gold" for r in plaid_store.read_cache())

    def test_an_unknown_card_is_refused(self, linked):
        client, _fake = linked
        item = client.post("/api/plaid/sandbox-link").json()["link"]["item_id"]
        response = client.post(
            "/api/plaid/map",
            json={"item_id": item, "account_id": "acct-gold", "card_id": "nope"},
        )
        assert response.status_code == 404

    def test_a_mapping_can_be_cleared(self, linked):
        client, _fake = linked
        item = client.post("/api/plaid/sandbox-link").json()["link"]["item_id"]
        client.post(
            "/api/plaid/map",
            json={"item_id": item, "account_id": "acct-gold", "card_id": "amex-gold"},
        )
        client.post(
            "/api/plaid/map",
            json={"item_id": item, "account_id": "acct-gold", "card_id": None},
        )
        link = plaid_store.read().links[0]
        assert link.card_for("acct-gold") is None


class TestSync:
    def test_sync_without_a_link_is_409(self, linked):
        client, _fake = linked
        assert client.post("/api/plaid/sync").status_code == 409

    def test_the_cursor_is_persisted(self, linked):
        """Losing it re-reads the whole history and duplicates every row."""
        client, fake = linked
        client.post("/api/plaid/sandbox-link")
        client.post("/api/plaid/sync")
        assert plaid_store.read().links[0].cursor == "cursor-1"

        client.post("/api/plaid/sync")
        assert fake.sync_calls == [None, "cursor-1"]

    def test_paging_continues_until_has_more_is_false(self, monkeypatch):
        pages = [
            {
                "added": [
                    PlaidTransaction(
                        transaction_id="p1",
                        account_id="acct-gold",
                        amount=D("10"),
                        on=date(2026, 10, 1),
                        name="One",
                    )
                ],
                "modified": [],
                "removed": [],
                "next_cursor": "c1",
                "has_more": True,
            },
            {
                "added": [
                    PlaidTransaction(
                        transaction_id="p2",
                        account_id="acct-gold",
                        amount=D("20"),
                        on=date(2026, 10, 2),
                        name="Two",
                    )
                ],
                "modified": [],
                "removed": [],
                "next_cursor": "c2",
                "has_more": False,
            },
        ]
        fake = FakePlaid(pages=pages)
        monkeypatch.setattr(routes_plaid, "PLAID", fake)
        client = TestClient(app)
        client.post("/api/plaid/sandbox-link")
        body = client.post("/api/plaid/sync").json()
        assert body["added"] == 2
        assert {r.transaction_id for r in plaid_store.read_cache()} == {"p1", "p2"}

    def test_a_removed_transaction_leaves_the_cache(self):
        """A reversed charge must stop being audited."""
        rows = [
            CachedTransaction(
                transaction_id="x",
                account_id="a",
                card_id="amex-gold",
                merchant_name="Gone",
                amount="10",
                on="2026-10-01",
            )
        ]
        plaid_store.write_cache(rows)
        plaid_store.merge_cache([], [], ["x"])
        assert plaid_store.read_cache() == []

    def test_a_modified_transaction_replaces_the_original(self):
        """Pending becomes posted, often at a different amount."""
        base = CachedTransaction(
            transaction_id="x",
            account_id="a",
            card_id="amex-gold",
            merchant_name="Dinner",
            amount="40.00",
            on="2026-10-01",
            pending=True,
        )
        plaid_store.write_cache([base])
        plaid_store.merge_cache([], [base.model_copy(update={"amount": "48.00", "pending": False})])
        rows = plaid_store.read_cache()
        assert len(rows) == 1
        assert rows[0].amount == "48.00"
        assert rows[0].pending is False


class TestTheFeed:
    def test_plaid_rows_reach_the_activity_feed(self, monkeypatch, tmp_path):
        """The whole point: a purchase we did not route, scored."""
        from pointwise import state

        plaid_store.write_cache(
            [
                CachedTransaction(
                    transaction_id="plaid-1",
                    account_id="acct-gold",
                    card_id="citi-double-cash",
                    merchant_name="Whole Foods",
                    amount="128.40",
                    on="2026-10-20",
                )
            ]
        )
        monkeypatch.setattr(state, "ledger", _EmptyLedger())
        rows, source = state.activity_feed()

        assert "plaid" in source
        got = next(r for r in rows if r.transaction_id == "plaid-1")
        assert got.card_id == "citi-double-cash"
        assert got.amount == D("128.40")

    def test_pending_rows_are_withheld(self, monkeypatch):
        """A pending amount changes. Scoring one would price the wrong figure."""
        from pointwise import state

        plaid_store.write_cache(
            [
                CachedTransaction(
                    transaction_id="pending-1",
                    account_id="a",
                    card_id="amex-gold",
                    merchant_name="Dinner",
                    amount="40.00",
                    on="2026-10-20",
                    pending=True,
                )
            ]
        )
        monkeypatch.setattr(state, "ledger", _EmptyLedger())
        rows, _source = state.activity_feed()
        assert not any(r.transaction_id == "pending-1" for r in rows)

    def test_a_purchase_we_routed_is_not_counted_twice(self, monkeypatch):
        """It posts to the card too, so Plaid reports it under another id.

        Double-counting would inflate both the earnings and any miss.
        """
        from pointwise import state
        from pointwise.ledger import LedgerEntry

        entry = LedgerEntry(
            transaction_id="ours",
            order_id="o1",
            merchant_name="Tartine Bakery",
            amount=D("96.00"),
            on=date(2026, 10, 27),
            card_id="amex-gold",
            capture_status="COMPLETED",
        )
        plaid_store.write_cache(
            [
                CachedTransaction(
                    transaction_id="plaid-dupe",
                    account_id="a",
                    card_id="amex-gold",
                    merchant_name="TARTINE BAKERY SF",
                    amount="96.00",
                    on="2026-10-27",
                )
            ]
        )
        monkeypatch.setattr(state, "ledger", _OneRowLedger(entry))
        rows, _source = state.activity_feed()
        assert [r.transaction_id for r in rows] == ["ours"]


class _EmptyLedger:
    @staticmethod
    def read():
        return []


class _OneRowLedger:
    def __init__(self, entry):
        self._entry = entry

    def read(self):
        return [self._entry]


class TestTheClientItself:
    def test_a_call_without_credentials_raises_rather_than_posting(self):
        from pointwise.plaid import PlaidClient

        client = PlaidClient(PlaidConfig(client_id=None, secret=None))
        with pytest.raises(PlaidNotConfigured):
            client.accounts("whatever")

    def test_amounts_go_through_str_not_float(self):
        """A float here loses cents, silently, on exactly the figures that matter."""
        from pointwise.plaid import PlaidClient

        row = PlaidClient._row(
            {
                "transaction_id": "t",
                "account_id": "a",
                "amount": 0.1 + 0.2,
                "date": "2026-10-01",
                "name": "Rounding",
            }
        )
        assert row.amount == D(str(0.1 + 0.2))

    def test_the_enriched_merchant_name_wins(self):
        """A raw feed string is unresolvable; the enriched one usually is not."""
        row = PlaidTransaction(
            transaction_id="t",
            account_id="a",
            amount=D("5"),
            on=date(2026, 10, 1),
            name="SQ *TARTINE BAKERY SF 0423",
            merchant_name="Tartine Bakery",
        )
        assert row.best_name == "Tartine Bakery"

    def test_it_falls_back_to_the_raw_name(self):
        row = PlaidTransaction(
            transaction_id="t",
            account_id="a",
            amount=D("5"),
            on=date(2026, 10, 1),
            name="SQ *SOMETHING 0423",
        )
        assert row.best_name == "SQ *SOMETHING 0423"


class TestOnlyScorablePurchasesAreKept:
    """Three filters, every one of them found by calling the real sandbox.

    The fake client in this file returned exactly the rows the code expected,
    which is the trap with fakes: it confirmed the happy path and hid all
    three of these.
    """

    def _txn(self, account_id, amount, category, tid="t"):
        return PlaidTransaction(
            transaction_id=tid,
            account_id=account_id,
            amount=Decimal(str(amount)),
            on=date(2026, 10, 20),
            name="Thing",
            merchant_name="Thing",
            category_primary=category,
        )

    def test_other_accounts_on_the_same_login_are_dropped(self):
        """A linked login carried 12 depository accounts alongside 2 cards.

        Thirty of the first forty-eight rows were chequing and savings, which
        have no card rules and can never be scored.
        """
        tracked = {"card-1"}
        assert routes_plaid._is_scorable(self._txn("card-1", 50, "FOOD_AND_DRINK"), tracked)
        assert not routes_plaid._is_scorable(
            self._txn("checking-1", 50, "FOOD_AND_DRINK"), tracked
        )

    @pytest.mark.parametrize(
        "category", ["LOAN_PAYMENTS", "TRANSFER_IN", "TRANSFER_OUT", "BANK_FEES", "INCOME"]
    )
    def test_non_purchases_are_dropped(self, category):
        """"AUTOMATIC PAYMENT - THANK YOU" is not a purchase.

        Auditing it would produce "you should have put your card payment on a
        different card".
        """
        assert not routes_plaid._is_scorable(
            self._txn("card-1", 2078.50, category), {"card-1"}
        )

    @pytest.mark.parametrize("amount", [-500, -4.22, 0])
    def test_non_positive_amounts_are_dropped(self, amount):
        """A refund is not a purchase, and `Purchase` requires amount > 0.

        This one did not merely add noise: a single refund row raised inside
        score() and returned a 500 for the entire activity screen.
        """
        assert not routes_plaid._is_scorable(
            self._txn("card-1", amount, "TRAVEL"), {"card-1"}
        )

    def test_the_feed_survives_a_stale_negative_row(self):
        """Defence in depth for a cache written before the filter existed."""
        from pointwise import state

        plaid_store.write_cache(
            [
                CachedTransaction(
                    transaction_id="refund",
                    account_id="a",
                    card_id="amex-gold",
                    merchant_name="United Airlines",
                    amount="-500",
                    on="2026-10-26",
                ),
                CachedTransaction(
                    transaction_id="real",
                    account_id="a",
                    card_id="amex-gold",
                    merchant_name="KFC",
                    amount="42.00",
                    on="2026-10-26",
                ),
            ]
        )
        rows, _source = state.activity_feed()
        ids = {r.transaction_id for r in rows}
        assert "refund" not in ids
        assert "real" in ids
