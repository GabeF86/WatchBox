import pytest
from fastapi.testclient import TestClient

from watchbox import db
from watchbox.app import create_app
from watchbox.config import Settings
from watchbox.valuation.models import Valuation


def val(estimate):
    return Valuation(estimate_usd=estimate, confidence="medium", tier=1, n_ebay=20, n_c24=8, ebay_median=11500.0,
                     ebay_p10=10500.0, ebay_p90=12900.0, ebay_min=9800.0, ebay_max=13300.0, c24_median=12400.0,
                     gap=0.07, w_ebay=0.7, w_c24=0.3, backtest_n=20, backtest_mdape=0.042, backtest_within10=0.9,
                     factors={})


class FakeService:
    source = "comps"

    def __init__(self):
        self.refreshed, self.recomputed = [], []

    def refresh_watch(self, conn, watch):
        self.refreshed.append(watch.id)
        db.add_valuation(conn, watch.id, val(11500.0))
        return True

    def recompute(self, conn, watch_id):
        self.recomputed.append(watch_id)
        db.add_valuation(conn, watch_id, val(9800.0))
        return True


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "t.db")


@pytest.fixture
def client(db_path, service):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=24, db_path=db_path)
    with TestClient(create_app(settings, service, run_scheduler=False)) as c:
        yield c


FORM = {"brand": "Rolex", "model": "Submariner Date", "reference": "116610LN", "slot": "4", "nickname": "",
        "price_reference": "", "year": "2015", "condition": "very_good", "box_papers": "full_set",
        "dial": "black", "bracelet": "oyster", "metal": "steel"}


def post(client, url, **changes):
    return client.post(url, data=FORM | changes, follow_redirects=False)


def test_details_are_saved_and_shown_in_the_edit_form(client):
    assert post(client, "/watches").status_code == 303
    page = client.get("/watches/1/edit").text
    assert 'value="very_good" selected' in page and 'value="black" selected' in page
    assert 'value="2015"' in page


def test_reference_is_optional(client):
    r = post(client, "/watches", reference="", brand="Glashütte Original", model="Sixties Panorama Date", slot="3")
    assert "error" not in r.headers["location"]


@pytest.mark.parametrize("field, bad", [("year", "1850"), ("year", "abc"), ("condition", "pristine"),
                                        ("dial", "purple")])
def test_invalid_details_are_rejected(client, field, bad):
    r = post(client, "/watches", **{field: bad})
    assert "error=" in r.headers["location"]


def test_breakdown_is_shown_on_the_index(client):
    post(client, "/watches")
    page = client.get("/").text
    assert "$11,500" in page
    assert "eBay sold (90 days" in page and "20 sales" in page
    assert "typical $10,500–$12,900 (low $9,800, high $13,300)" in page
    assert "adjusted for your watch's condition and box &amp; papers" in page
    assert "Chrono24 asking: 8 listings" in page
    assert "within ±4.2%" in page
    assert "medium confidence" in page


def test_breakdown_handles_missing_source_stats(client, db_path):
    post(client, "/watches")
    conn = db.connect(db_path)
    try:
        db.add_valuation(conn, 1, Valuation(
            estimate_usd=12000.0, confidence="low", tier=2, n_ebay=0, n_c24=0, ebay_median=None, ebay_p10=None,
            ebay_p90=None, ebay_min=None, ebay_max=None, c24_median=None, gap=0.0, w_ebay=0.0, w_c24=1.0,
            backtest_n=0, backtest_mdape=None, backtest_within10=None, factors={}))
    finally:
        conn.close()
    r = client.get("/")
    assert r.status_code == 200
    assert "eBay sold: not enough sales" in r.text
    assert "Chrono24: no listings" in r.text
    assert "Backtest: not enough sales yet" in r.text


def test_detail_edit_recomputes_without_refetching(client, service):
    post(client, "/watches")
    post(client, "/watches/1", condition="good")
    assert service.refreshed == [1] and service.recomputed == [1]
    assert "$9,800" in client.get("/").text


def test_reference_edit_refetches(client, service):
    post(client, "/watches")
    post(client, "/watches/1", reference="126610LN")
    assert service.refreshed == [1, 1] and service.recomputed == []
