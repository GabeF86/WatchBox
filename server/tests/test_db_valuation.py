import sqlite3
from datetime import date

import pytest

from watchbox import db
from watchbox.pricing import PriceResult
from watchbox.valuation.models import Comparable, Valuation


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def val(estimate=11500.0, **kw):
    base = dict(estimate_usd=estimate, confidence="high", tier=1, n_ebay=20, n_c24=8, ebay_median=11500.0,
                ebay_p10=10500.0, ebay_p90=12900.0, ebay_min=9800.0, ebay_max=13300.0, c24_median=12400.0,
                gap=0.07, w_ebay=0.7, w_c24=0.3, backtest_n=20, backtest_mdape=0.04, backtest_within10=0.9,
                factors={"box": {"full_set": 1.0}})
    return Valuation(**(base | kw))


def comp(source="ebay", price=11000.0):
    return Comparable(source=source, kind="sold" if source == "ebay" else "asking", price_usd=price,
                      date=date(2026, 9, 30), title="Rolex 116610LN", box_papers="full_set", best_offer=False)


def test_details_are_stored_and_build_the_query(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 4, None, year=2015, condition="good",
                       box_papers="watch_only", dial="black", bracelet="oyster", metal="steel")
    w = db.get_watch(conn, wid)
    assert (w.year, w.condition, w.box_papers, w.dial, w.bracelet, w.metal) == (
        2015, "good", "watch_only", "black", "oyster", "steel")
    assert w.query.reference == "116610LN" and w.query.condition == "good"


def test_defaults_and_optional_reference(conn):
    w = db.get_watch(conn, db.add_watch(conn, "Glashütte Original", "Sixties Panorama Date", "", None, None))
    assert (w.reference, w.condition, w.box_papers, w.year) == ("", "excellent", "full_set", None)


def test_comparables_are_replaced_per_source_and_round_trip(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "ebay", [comp("ebay")] * 3)
    db.replace_comparables(conn, wid, "chrono24", [comp("chrono24")] * 2)
    db.replace_comparables(conn, wid, "ebay", [comp("ebay", 12000.0)])
    loaded = db.load_comparables(conn, wid)
    assert sorted((c.source, c.price_usd) for c in loaded) == [("chrono24", 11000.0), ("chrono24", 11000.0),
                                                               ("ebay", 12000.0)]
    assert loaded[0].date == date(2026, 9, 30) and loaded[0].box_papers == "full_set"


def test_latest_valuation_becomes_the_price(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)
    db.add_price(conn, wid, PriceResult(12413.0, 270, "thewatchapi", as_of="2024-07-17"),
                 fetched_at="2026-09-01T00:00:00+00:00")
    db.add_valuation(conn, wid, val(11000.0), as_of="2026-10-01T00:00:00+00:00")
    db.add_valuation(conn, wid, val(11500.0, confidence="low", failed_sources=("chrono24",)),
                     as_of="2026-10-02T00:00:00+00:00")
    w = db.get_watch(conn, wid)
    assert (w.price_usd, w.price_source, w.price_date, w.confidence, w.sample_size) == (
        11500.0, "comps", None, "low", 28)
    latest = db.latest_valuation(conn, wid)
    assert latest["failed_sources"] == ("chrono24",) and latest["factors"] == {"box": {"full_set": 1.0}}
    assert db.latest_valuations(conn)[wid]["estimate_usd"] == 11500.0
    assert db.latest_fetch_time(conn) == "2026-10-02T00:00:00+00:00"


def test_identity_change_clears_market_data_but_detail_change_keeps_it(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "ebay", [comp()])
    db.add_valuation(conn, wid, val())
    db.update_watch(conn, wid, "Rolex", "Submariner", "116610LN", 1, None, condition="good")
    assert db.load_comparables(conn, wid) and db.latest_valuation(conn, wid)
    db.update_watch(conn, wid, "Rolex", "Submariner", "126610LN", 1, None)
    assert db.load_comparables(conn, wid) == [] and db.latest_valuation(conn, wid) is None


def test_model_change_without_reference_clears_market_data(conn):
    wid = db.add_watch(conn, "Glashütte Original", "Sixties", "", 3, None)
    db.add_valuation(conn, wid, val())
    db.update_watch(conn, wid, "Glashütte Original", "Sixties Panorama Date", "", 3, None)
    assert db.latest_valuation(conn, wid) is None


def test_old_databases_are_migrated(tmp_path):
    path = tmp_path / "v0.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE watches (id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL, model TEXT NOT NULL,
            reference TEXT NOT NULL, slot INTEGER UNIQUE CHECK (slot BETWEEN 1 AND 8), nickname TEXT,
            created_at TEXT NOT NULL);
        CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER NOT NULL REFERENCES watches(id)
            ON DELETE CASCADE, price_usd REAL NOT NULL, sample_size INTEGER NOT NULL, source TEXT NOT NULL,
            fetched_at TEXT NOT NULL);
        INSERT INTO watches (brand, model, reference, slot, nickname, created_at)
            VALUES ('Rolex', 'Submariner', '116610LN', 4, NULL, '2026-09-29T00:00:00+00:00');
    """)
    old.commit()
    old.close()
    conn = db.connect(path)
    try:
        w = db.list_watches(conn)[0]
        assert (w.condition, w.box_papers, w.year, w.price_reference) == ("excellent", "full_set", None, None)
        db.add_valuation(conn, w.id, val())
        assert db.get_watch(conn, w.id).price_usd == 11500.0
    finally:
        conn.close()
