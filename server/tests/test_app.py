import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from watchbox.app import create_app, run_scheduled
from watchbox.config import Settings
from watchbox.pricing import PriceResult


class FakeProvider:
    def __init__(self, prices):
        self.prices = prices
        self.calls = []

    def get_price(self, brand, reference):
        self.calls.append(reference)
        price = self.prices.get(reference)
        return PriceResult(price, 10, "fake") if price is not None else None


@pytest.fixture
def provider():
    return FakeProvider({"126610LN": 13400.0, "310.30.42.50.01.001": 6150.0})


@pytest.fixture
def client(tmp_path, provider):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=6, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, provider, run_scheduler=False)) as c:
        yield c


def add(client, **form):
    data = {"brand": "Rolex", "model": "Submariner", "reference": "126610LN", "slot": "", "nickname": ""} | form
    return client.post("/watches", data=data, follow_redirects=False)


def test_display_when_empty(client):
    body = client.get("/api/display").json()
    assert body["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]
    assert "generated_at" in body


def test_adding_a_watch_prices_it_and_shows_it_on_the_display(client, provider):
    response = add(client, slot="1")
    assert response.status_code == 303
    assert provider.calls == ["126610LN"]
    assert client.get("/api/display").json()["screens"] == [
        {"line1": "TOTAL 1 watch", "line2": "$13,400"},
        {"line1": "1 Submariner", "line2": "$13,400"},
    ]


def test_index_lists_watches_and_total(client):
    add(client, slot="1")
    page = client.get("/").text
    assert "Submariner" in page
    assert "$13,400" in page


def test_duplicate_slot_shows_error(client):
    add(client, slot="1")
    response = add(client, brand="Omega", model="Speedmaster", reference="310.30.42.50.01.001", slot="1")
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert "Slot 1 is already taken" in client.get(response.headers["location"]).text


def test_invalid_slot_is_rejected(client):
    response = add(client, slot="9")
    assert "error=" in response.headers["location"]
    assert client.get("/api/display").json()["screens"][0]["line1"] == "No watches yet"


def test_edit_page_prefills_form(client):
    add(client, slot="1")
    page = client.get("/watches/1/edit").text
    assert 'value="126610LN"' in page


def test_edit_missing_watch_is_404(client):
    assert client.get("/watches/99/edit").status_code == 404


def test_edit_then_delete(client):
    add(client, slot="1")
    response = client.post(
        "/watches/1",
        data={"brand": "Rolex", "model": "Submariner", "reference": "126610LN", "slot": "4", "nickname": "Sub"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/api/display").json()["screens"][1]["line1"] == "4 Sub"
    client.post("/watches/1/delete", follow_redirects=False)
    assert client.get("/api/display").json()["screens"][0]["line1"] == "No watches yet"


def test_refresh_now_reprices_everything(client, provider):
    add(client, slot="1")
    provider.calls.clear()
    response = client.post("/refresh", follow_redirects=False)
    assert response.status_code == 303
    assert provider.calls == ["126610LN"]


def test_missing_provider_shows_banner(tmp_path):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=6, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, None, run_scheduler=False)) as c:
        assert "No price source configured" in c.get("/").text
        assert c.post("/watches", data={"brand": "Rolex", "model": "Sub", "reference": "1", "slot": "", "nickname": ""},
                      follow_redirects=False).status_code == 303


def test_reference_without_letters_or_digits_is_rejected(client):
    response = add(client, reference="-")
    assert "error=" in response.headers["location"]
    assert response.headers["location"].startswith("/?error=")
    assert client.get("/api/display").json()["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]


def test_whitespace_only_brand_or_model_is_rejected(client):
    response = add(client, brand="   ")
    assert "error=" in response.headers["location"]
    assert client.get("/api/display").json()["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]

    response = add(client, model="\t\n")
    assert "error=" in response.headers["location"]
    assert client.get("/api/display").json()["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]


def test_run_scheduled_logs_and_swallows_exceptions(caplog):
    def boom():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="watchbox.app"):
        asyncio.run(run_scheduled(boom))
    assert "scheduled refresh failed" in caplog.text


def test_run_scheduled_runs_a_working_job(tmp_path):
    calls = []
    asyncio.run(run_scheduled(lambda: calls.append(1)))
    assert calls == [1]


def test_lifespan_cancels_scheduler_task_cleanly(tmp_path, provider):
    settings = Settings(ebay_client_id="x", ebay_client_secret="x", refresh_hours=1000, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, provider, run_scheduler=True)) as c:
        c.get("/api/display")
    # If the scheduler task wasn't cancelled and awaited cleanly, this would raise or hang.


class WatchApiLikeProvider(FakeProvider):
    source = "thewatchapi"

    def get_price(self, brand, reference):
        self.calls.append(reference)
        return PriceResult(13400.0, 5, "thewatchapi", as_of="2024-07-17")


def test_index_labels_thewatchapi_prices_without_listing_counts(tmp_path):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=24, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, WatchApiLikeProvider({}), run_scheduler=False)) as c:
        c.post("/watches", data={"brand": "Rolex", "model": "Submariner", "reference": "126610LN", "slot": "1",
                                 "nickname": ""}, follow_redirects=False)
        page = c.get("/").text
        assert "TheWatchAPI" in page
        assert "listings" not in page
        assert "$13,400" in page
        assert "data from 2024-07-17" in page


def test_price_reference_field_is_used_and_shown(client, provider):
    provider.prices["2-39-47-06-02-04"] = 6779.0
    add(client, brand="Glashütte Original", model="Sixties Panorama Date", reference="2-39-47-01-01-04",
        slot="3", price_reference="2-39-47-06-02-04")
    assert provider.calls == ["2-39-47-06-02-04"]
    page = client.get("/").text
    assert "estimated from 2-39-47-06-02-04" in page
    assert client.get("/watches/1/edit").text.count('value="2-39-47-06-02-04"') == 1
    assert client.get("/api/display").json()["screens"][1]["line2"].startswith("~$6,779")


def test_run_exclusive_skips_when_already_running():
    import threading

    from watchbox.app import run_exclusive
    lock, calls = threading.Lock(), []
    assert run_exclusive(lock, lambda: calls.append(1)) is True
    assert not lock.locked()
    with lock:
        assert run_exclusive(lock, lambda: calls.append(2)) is False
    assert calls == [1]
