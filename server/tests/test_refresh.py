from datetime import datetime, timezone

from watchbox import db
from watchbox.pricing import PriceResult
from watchbox.refresh import needs_refresh, refresh_all


def test_needs_refresh():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert needs_refresh(None, 6, now)
    assert needs_refresh("2026-09-27T05:59:00+00:00", 6, now)
    assert not needs_refresh("2026-09-27T07:00:00+00:00", 6, now)


def test_refresh_all_stores_prices_and_survives_failures(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ok = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    broken = db.add_watch(conn, "Omega", "Speedmaster", "BROKEN", 2, None)
    thin = db.add_watch(conn, "Tudor", "Black Bay", "THIN", 3, None)

    class Provider:
        def get_price(self, brand, reference):
            if reference == "BROKEN":
                raise RuntimeError("eBay down")
            if reference == "THIN":
                return None
            return PriceResult(13400.0, 10, "fake")

    assert refresh_all(conn, Provider()) == 1
    prices = {w.id: w.price_usd for w in db.list_watches(conn)}
    assert prices == {ok: 13400.0, broken: None, thin: None}


def test_refresh_all_skips_watch_deleted_during_fetch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    watch_id = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)

    class Provider:
        def get_price(self, brand, reference):
            db.delete_watch(conn, watch_id)
            return PriceResult(13400.0, 10, "fake")

    assert refresh_all(conn, Provider()) == 0
    assert db.list_watches(conn) == []


def test_refresh_watch_skips_storing_when_reference_changed_during_fetch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    watch_id = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    watch = db.get_watch(conn, watch_id)

    class Provider:
        def get_price(self, brand, reference):
            db.update_watch(conn, watch_id, "Rolex", "Submariner", "DIFFERENT", 1, None)
            return PriceResult(13400.0, 10, "fake")

    from watchbox.refresh import refresh_watch

    assert refresh_watch(conn, Provider(), watch) is False
    assert db.get_watch(conn, watch_id).price_usd is None
