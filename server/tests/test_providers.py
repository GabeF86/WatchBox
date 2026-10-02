from watchbox.config import Settings
from watchbox.ebay import EbayBrowseProvider
from watchbox.providers import make_provider
from watchbox.watchapi import TheWatchApiProvider


def settings(**overrides):
    base = dict(ebay_client_id="", ebay_client_secret="", refresh_hours=24, db_path="x.db",
                watchapi_token="", price_source="auto", apify_token="")
    return Settings(**(base | overrides))


def test_auto_prefers_thewatchapi_when_token_set():
    s = settings(watchapi_token="t", ebay_client_id="id", ebay_client_secret="sec")
    assert isinstance(make_provider(s), TheWatchApiProvider)


def test_auto_falls_back_to_ebay():
    assert isinstance(make_provider(settings(ebay_client_id="id", ebay_client_secret="sec")), EbayBrowseProvider)


def test_auto_with_no_keys_is_none():
    assert make_provider(settings()) is None


def test_explicit_source_without_its_key_is_none():
    assert make_provider(settings(price_source="thewatchapi", ebay_client_id="id", ebay_client_secret="sec")) is None
    assert make_provider(settings(price_source="ebay", watchapi_token="t")) is None


def test_unknown_source_is_none():
    assert make_provider(settings(price_source="chrono24", watchapi_token="t")) is None


def test_auto_prefers_comps_when_apify_token_set():
    from watchbox.valuation.service import ValuationService
    s = settings(apify_token="a", watchapi_token="t")
    assert isinstance(make_provider(s), ValuationService)
    assert isinstance(make_provider(settings(price_source="thewatchapi", watchapi_token="t", apify_token="a")),
                      TheWatchApiProvider)
