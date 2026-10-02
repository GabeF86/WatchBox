from datetime import date

import pytest

from watchbox import db, refresh
from watchbox.valuation.models import Comparable, Valuation
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


def test_model_rename_with_a_reference_during_fetch_keeps_the_result(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)

    class RenamingSource(FakeSource):
        def fetch(self, query):
            db.update_watch(conn, wid, "Rolex", "Submariner Date", "116610LN", 1, None)
            return comps("ebay")

    assert ValuationService([RenamingSource("ebay", None)]).refresh_watch(conn, db.get_watch(conn, wid))
    assert len(db.load_comparables(conn, wid)) == 6


def test_one_watch_failing_to_value_does_not_stop_the_others(conn, monkeypatch):
    from watchbox.valuation import service as service_module
    first = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    second = db.add_watch(conn, "Rolex", "Submariner Date", "126610LN", 2, None)
    real_value = service_module.value

    def flaky_value(query, *args, **kwargs):
        if query.reference == "116610LN":
            raise RuntimeError("boom")
        return real_value(query, *args, **kwargs)

    monkeypatch.setattr(service_module, "value", flaky_value)
    service = ValuationService([FakeSource("ebay", comps("ebay"))])
    assert refresh.refresh_all(conn, service) == 1
    assert db.latest_valuation(conn, first) is None and db.latest_valuation(conn, second)


def test_unexpected_source_errors_are_logged_with_a_trace_and_marked_failed(conn, caplog):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    service = ValuationService([FakeSource("ebay", comps("ebay")), FakeSource("chrono24", KeyError("bug"))])
    assert service.refresh_watch(conn, db.get_watch(conn, wid))
    assert db.latest_valuation(conn, wid)["failed_sources"] == ("chrono24",)
    assert any(r.exc_info and "chrono24" in r.getMessage() for r in caplog.records)


def test_expected_source_errors_are_logged_without_a_trace(conn, caplog):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    service = ValuationService([FakeSource("ebay", comps("ebay")), FakeSource("chrono24", SourceError("down"))])
    assert service.refresh_watch(conn, db.get_watch(conn, wid))
    records = [r for r in caplog.records if "chrono24" in r.getMessage()]
    assert records and not any(r.exc_info for r in records)


def test_valuations_are_dated_by_their_comparables_so_recompute_is_not_fresh_data(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    service = ValuationService([FakeSource("ebay", comps("ebay", 10000.0))])
    service.refresh_watch(conn, db.get_watch(conn, wid))
    fetched_at = db.latest_comparables_time(conn, wid)
    assert fetched_at and db.latest_valuation(conn, wid)["as_of"] == fetched_at
    last_fetch = db.latest_fetch_time(conn)
    db.update_watch(conn, wid, "Rolex", "Submariner Date", "116610LN", 1, None, box_papers="watch_only")
    assert service.recompute(conn, wid)
    latest = db.latest_valuation(conn, wid)
    assert latest["as_of"] == fetched_at and db.latest_fetch_time(conn) == last_fetch
    assert latest["estimate_usd"] == db.get_watch(conn, wid).price_usd < 10000.0  # the recomputed one


def test_recompute_wins_over_an_older_valuation_dated_later(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "ebay", comps("ebay", 10000.0), fetched_at="2026-10-01T00:00:00+00:00")
    service = ValuationService([])
    assert service.recompute(conn, wid)
    first = db.latest_valuation(conn, wid)
    db.add_valuation(conn, wid, Valuation(**{**{k: first[k] for k in db.VALUATION_COLUMNS}, "factors": {}}),
                     as_of="2026-10-02T00:00:00+00:00")  # e.g. stored by an older version, dated "now"
    db.update_watch(conn, wid, "Rolex", "Submariner Date", "116610LN", 1, None, box_papers="watch_only")
    assert service.recompute(conn, wid)
    assert db.latest_valuation(conn, wid)["estimate_usd"] < first["estimate_usd"]
