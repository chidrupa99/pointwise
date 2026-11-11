"""The local record of purchases we executed."""

from datetime import date
from decimal import Decimal


from pointwise import ledger

D = Decimal


def entry(txn_id: str = "C-1", card_id: str = "amex-gold") -> ledger.LedgerEntry:
    return ledger.LedgerEntry(
        transaction_id=txn_id,
        order_id="O-1",
        merchant_name="Trader Joe's",
        amount=D("64.20"),
        on=date(2026, 10, 26),
        card_id=card_id,
        capture_status="COMPLETED",
    )


def test_missing_file_reads_as_empty(tmp_path):
    assert ledger.read(tmp_path / "nope.json") == []


def test_append_then_read_round_trips(tmp_path):
    path = tmp_path / "ledger.json"
    ledger.append(entry(), path)
    rows = ledger.read(path)
    assert len(rows) == 1
    assert rows[0].amount == D("64.20")
    assert rows[0].card_id == "amex-gold"


def test_append_accumulates(tmp_path):
    path = tmp_path / "ledger.json"
    ledger.append(entry("C-1"), path)
    ledger.append(entry("C-2", "capital-one-venture-x"), path)
    rows = ledger.read(path)
    assert [r.transaction_id for r in rows] == ["C-1", "C-2"]


def test_corrupt_file_reads_as_empty_rather_than_crashing(tmp_path):
    """A broken ledger must not take the whole app down."""
    path = tmp_path / "ledger.json"
    path.write_text("{ not json")
    assert ledger.read(path) == []


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "ledger.json"
    ledger.append(entry(), path)
    ledger.append(entry("C-2"), path)
    assert list(tmp_path.glob("*.tmp")) == []
    assert len(ledger.read(path)) == 2


def test_amount_survives_as_decimal_not_float(tmp_path):
    """Money through JSON must not pick up binary float error."""
    path = tmp_path / "ledger.json"
    ledger.append(
        ledger.LedgerEntry(
            transaction_id="C-9",
            order_id="O-9",
            merchant_name="X",
            amount=D("0.70"),
            on=date(2026, 10, 26),
            card_id="amex-gold",
            capture_status="COMPLETED",
        ),
        path,
    )
    assert ledger.read(path)[0].amount == D("0.70")
