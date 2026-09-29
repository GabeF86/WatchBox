import httpx
import pytest

from watchbox.watchapi import PRICE_HISTORY_URL, TheWatchApiProvider, WatchApiError


def make_provider(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TheWatchApiProvider("secret-token", http=http)


def history(brand="Rolex", reference="126610LN", points=()):
    return {"meta": {"brand": brand, "reference_number": reference},
            "data": [{"date": d, "price": p} for d, p in points]}


def test_get_price_uses_latest_point_and_records_its_date():
    def handler(request):
        assert str(request.url).startswith(PRICE_HISTORY_URL)
        assert request.url.params["api_token"] == "secret-token"
        assert request.url.params["reference_number"] == "126610LN"
        assert "date_from" not in request.url.params  # their data can lag; take the newest they have
        return httpx.Response(200, json=history(points=[
            ("2026-09-27T00:00:00.000Z", 13420.5),
            ("2026-09-01T00:00:00.000Z", 13100.0),
        ]))

    result = make_provider(handler).get_price("Rolex", "126610LN")
    assert (result.price_usd, result.sample_size, result.source, result.as_of) == (13420.5, 2, "thewatchapi", "2026-09-27")


def test_no_data_returns_none():
    assert make_provider(lambda r: httpx.Response(200, json=history())).get_price("Rolex", "126610LN") is None


def test_brand_mismatch_returns_none():
    response = history(brand="Omega", points=[("2026-09-27T00:00:00.000Z", 5000.0)])
    assert make_provider(lambda r: httpx.Response(200, json=response)).get_price("Rolex", "126610LN") is None


def test_brand_match_ignores_case_and_punctuation():
    response = history(brand="A. Lange & Söhne", reference="191.039",
                       points=[("2026-09-27T00:00:00.000Z", 40000.0)])
    result = make_provider(lambda r: httpx.Response(200, json=response)).get_price("a lange & sohne", "191.039")
    assert result.price_usd == 40000.0


def test_plan_error_explains_itself_without_leaking_token():
    body = {"error": {"code": "insufficient_plan", "message": "This endpoint requires the Standard plan"}}
    provider = make_provider(lambda r: httpx.Response(403, json=body))
    with pytest.raises(WatchApiError) as exc:
        provider.get_price("Rolex", "126610LN")
    message = str(exc.value)
    assert "403" in message and "insufficient_plan" in message and "plan" in message.lower()
    assert "secret-token" not in message


def test_unparseable_error_body_still_raises():
    with pytest.raises(WatchApiError, match="500"):
        make_provider(lambda r: httpx.Response(500, text="oops")).get_price("Rolex", "126610LN")
