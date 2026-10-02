from datetime import date

import pytest

from watchbox import db, refresh
from watchbox.valuation.models import Comparable
from watchbox.valuation.service import ValuationService
from watchbox.valuation.sources.apify import SourceError


def comps(source, price=11000.0, n=6):
    kind = "sold" if source == "ebay" else "asking"
    return [Comparable(source=source, kind=kind, price_usd=price + i, date=date(2026, 9, 30),
                       title="Rolex Submariner Date 116610LN") for i in range(n)]


class FakeSource:
    def __init__(self, name, result):
        self.name, self.result, self.calls = name, result, 0

    def fetch(self, query):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_refresh_stores_comparables_and_a_valuation(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    service = ValuationService([FakeSource("ebay", comps("ebay")), FakeSource("chrono24", comps("chrono24", 12000))])
    assert refresh.refresh_watch(conn, service, db.get_watch(conn, wid))  # delegated by watchbox.refresh
    w = db.get_watch(conn, wid)
    assert w.price_source == "comps" and 10_000 < w.price_usd < 12_500
    assert len(db.load_comparables(conn, wid)) == 12


def test_one_failed_source_keeps_its_old_comparables_and_lowers_confidence(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "chrono24", comps("chrono24", 12000))
    service = ValuationService([FakeSource("ebay", comps("ebay", n=12)), FakeSource("chrono24", SourceError("x"))])
    assert service.refresh_watch(conn, db.get_watch(conn, wid))
    assert len(db.load_comparables(conn, wid)) == 18
    assert db.latest_valuation(conn, wid)["failed_sources"] == ("chrono24",)


def test_all_sources_failing_keeps_previous_valuation(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    good = ValuationService([FakeSource("ebay", comps("ebay"))])
    good.refresh_watch(conn, db.get_watch(conn, wid))
    before = db.get_watch(conn, wid).price_usd
    bad = ValuationService([FakeSource("ebay", SourceError("down"))])
    assert not bad.refresh_watch(conn, db.get_watch(conn, wid))
    assert db.get_watch(conn, wid).price_usd == before


def test_recompute_uses_stored_comparables_without_fetching(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    source = FakeSource("ebay", comps("ebay", 10000.0))
    service = ValuationService([source])
    service.refresh_watch(conn, db.get_watch(conn, wid))
    full_set = db.get_watch(conn, wid).price_usd
    db.update_watch(conn, wid, "Rolex", "Submariner Date", "116610LN", 1, None, box_papers="watch_only")
    assert service.recompute(conn, wid)
    assert source.calls == 1
    assert db.get_watch(conn, wid).price_usd < full_set


def test_result_is_discarded_if_watch_changes_during_fetch(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)

    class EditingSource(FakeSource):
        def fetch(self, query):
            db.update_watch(conn, wid, "Rolex", "Submariner Date", "126610LN", 1, None)
            return comps("ebay")

    assert not ValuationService([EditingSource("ebay", None)]).refresh_watch(conn, db.get_watch(conn, wid))
    assert db.load_comparables(conn, wid) == []
