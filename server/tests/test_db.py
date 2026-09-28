import pytest

from watchbox import db
from watchbox.pricing import PriceResult


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_add_and_list_uses_latest_price(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"), fetched_at="2026-09-27T10:00:00+00:00")
    db.add_price(conn, wid, PriceResult(13400.0, 22, "ebay"), fetched_at="2026-09-27T16:00:00+00:00")
    [w] = db.list_watches(conn)
    assert (w.id, w.model, w.slot, w.price_usd, w.sample_size) == (wid, "Submariner", 1, 13400.0, 22)
    assert db.latest_fetch_time(conn) == "2026-09-27T16:00:00+00:00"


def test_list_orders_by_slot_with_unslotted_last(conn):
    db.add_watch(conn, "Cartier", "Tank Must", "WSTA0041", None, None)
    db.add_watch(conn, "Omega", "Speedmaster", "310.30.42.50.01.001", 2, None)
    db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    assert [w.model for w in db.list_watches(conn)] == ["Submariner", "Speedmaster", "Tank Must"]


def test_slot_must_be_unique(conn):
    db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    with pytest.raises(db.SlotTakenError, match="Slot 1 is already taken"):
        db.add_watch(conn, "Omega", "Speedmaster", "310.30.42.50.01.001", 1, None)


def test_update_keeps_prices_when_reference_unchanged(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.update_watch(conn, wid, "Rolex", "Submariner Date", "126610LN", 2, "Sub")
    w = db.get_watch(conn, wid)
    assert (w.model, w.slot, w.nickname, w.price_usd) == ("Submariner Date", 2, "Sub", 13000.0)


def test_update_clears_prices_when_reference_changes(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.update_watch(conn, wid, "Rolex", "GMT-Master II", "126710BLRO", 1, None)
    assert db.get_watch(conn, wid).price_usd is None


def test_update_clears_prices_when_only_brand_changes(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.update_watch(conn, wid, "Tudor", "Submariner", "126610LN", 1, None)
    assert db.get_watch(conn, wid).price_usd is None


def test_delete_removes_watch_and_prices(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.delete_watch(conn, wid)
    assert db.list_watches(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0


def test_get_missing_watch_returns_none(conn):
    assert db.get_watch(conn, 999) is None
