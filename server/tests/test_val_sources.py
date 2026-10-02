import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from watchbox.valuation.models import WatchQuery
from watchbox.valuation.sources.apify import ApifyClient, SourceError
from watchbox.valuation.sources.chrono24 import ApifyChrono24Source, search_url
from watchbox.valuation.sources.ebay_sold import ApifyEbaySoldSource, ebay_query, parse_sold_date

FIXTURES = Path(__file__).parent / "fixtures"
EBAY_ROWS = json.loads((FIXTURES / "ebay_sold_116610ln.json").read_text())
C24_ROWS = json.loads((FIXTURES / "chrono24_116610ln.json").read_text())
SUB = WatchQuery(brand="Rolex", model="Submariner Date", reference="116610LN")


def client(handler):
    return ApifyClient("secret-token", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_posts_with_bearer_token_and_returns_rows():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert "/acts/memo23~ebay-search-scraper-ppe/run-sync-get-dataset-items" in str(request.url)
        return httpx.Response(201, json=[{"a": 1}])

    assert client(handler).run("memo23/ebay-search-scraper-ppe", {}) == [{"a": 1}]


def test_client_errors_never_include_the_token():
    def handler(request):
        return httpx.Response(400, json={"error": {"type": "run-failed", "message": "Actor run did not succeed"}})

    with pytest.raises(SourceError) as exc:
        client(handler).run("memo23/x", {})
    assert "400" in str(exc.value) and "did not succeed" in str(exc.value)
    assert "secret-token" not in str(exc.value)


def test_client_rejects_non_list_and_transport_errors():
    with pytest.raises(SourceError):
        client(lambda r: httpx.Response(200, json={"not": "a list"})).run("memo23/x", {})

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(SourceError, match="request failed"):
        client(boom).run("memo23/x", {})


def test_ebay_query_and_payload():
    assert ebay_query(SUB) == "Rolex 116610LN"
    assert ebay_query(WatchQuery(brand="Rolex", model="Datejust 41", dial="blue")) == "Rolex Datejust 41 blue"
    payload = ApifyEbaySoldSource(None).payload(SUB)
    assert payload["mode"] == "sold" and payload["soldWithinDays"] == 90 and payload["category"] == "31387"
    assert payload["searchQuery"] == "Rolex 116610LN"


def test_parse_sold_date():
    assert parse_sold_date("Sold  Oct 1, 2026") == date(2026, 10, 1)
    assert parse_sold_date(None) is None


def test_ebay_source_parses_fixture():
    comps = ApifyEbaySoldSource(client(lambda r: httpx.Response(201, json=EBAY_ROWS))).fetch(SUB)
    assert len(comps) == 30  # the summary row is skipped
    assert sum(c.best_offer for c in comps) == 4
    assert all(c.source == "ebay" and c.kind == "sold" and c.price_usd > 0 for c in comps)
    assert any(c.box_papers == "full_set" for c in comps)


def test_chrono24_search_url():
    url = search_url(SUB)
    assert "query=Rolex+116610LN" in url and "currencyId=USD" in url


def test_chrono24_source_parses_fixture_details():
    comps = ApifyChrono24Source(client(lambda r: httpx.Response(201, json=C24_ROWS))).fetch(SUB)
    assert len(comps) == 12
    first = comps[0]
    assert (first.price_usd, first.condition, first.box_papers, first.year, first.dial, first.metal) == (
        11200.0, "good", "watch_only", 2015, "black", "steel")
    assert first.reference == "126610LN" and "116610LN" in first.title  # mislabelled reference, real one in the title
    assert comps[1].box_papers == "full_set" and comps[1].condition == "very_good"
    assert comps[5].year == 2014  # "2014 (Approximation)"
    assert comps[10].condition == "new"  # "Like new & unworn"
