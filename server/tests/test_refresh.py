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
