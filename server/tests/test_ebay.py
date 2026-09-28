import json
from pathlib import Path

import httpx
import pytest

from watchbox.ebay import TOKEN_URL, EbayBrowseProvider, EbayError

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ebay_search_126610ln.json").read_text())


def make_provider(handler, clock=lambda: 0.0):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return EbayBrowseProvider("id", "secret", http=http, clock=clock)


def token_response(token="tok"):
    return httpx.Response(200, json={"access_token": token, "expires_in": 7200})


def test_get_price_authenticates_searches_and_summarizes():
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            assert request.headers["Authorization"].startswith("Basic ")
            return token_response()
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
        assert request.url.params["q"] == "Rolex 126610LN"
        assert request.url.params["category_ids"] == "31387"
        return httpx.Response(200, json=FIXTURE)

    result = make_provider(handler).get_price("Rolex", "126610LN")
    assert (result.price_usd, result.sample_size, result.source) == (13250.0, 4, "ebay")


def test_search_skips_non_usd_prices():
    def handler(request):
        return token_response() if str(request.url).startswith(TOKEN_URL) else httpx.Response(200, json=FIXTURE)

    listings = make_provider(handler).search("Rolex", "126610LN")
    assert len(listings) == 7
    assert all(isinstance(price, float) for _, price in listings)


def test_token_is_cached_until_expiry():
    token_calls = 0
    now = [0.0]

    def handler(request):
        nonlocal token_calls
        if str(request.url).startswith(TOKEN_URL):
            token_calls += 1
            return token_response(f"tok{token_calls}")
        return httpx.Response(200, json={"itemSummaries": []})

    provider = make_provider(handler, clock=lambda: now[0])
    provider.search("Rolex", "126610LN")
    provider.search("Rolex", "126610LN")
    assert token_calls == 1
    now[0] = 7200.0
    provider.search("Rolex", "126610LN")
    assert token_calls == 2


def test_search_error_raises():
    def handler(request):
        return token_response() if str(request.url).startswith(TOKEN_URL) else httpx.Response(500, text="boom")

    with pytest.raises(EbayError, match="500"):
        make_provider(handler).search("Rolex", "126610LN")


def test_token_error_raises():
    with pytest.raises(EbayError, match="401"):
        make_provider(lambda request: httpx.Response(401, text="bad creds")).search("Rolex", "126610LN")
