"""Picks the price provider (PRICE_SOURCE=auto prefers the valuation engine, then TheWatchAPI, then eBay)."""
import logging

from .config import Settings
from .ebay import EbayBrowseProvider
from .pricing import PriceProvider
from .valuation.service import ValuationService
from .valuation.sources.apify import ApifyClient
from .valuation.sources.chrono24 import ApifyChrono24Source
from .valuation.sources.ebay_sold import ApifyEbaySoldSource
from .watchapi import TheWatchApiProvider

log = logging.getLogger("watchbox.providers")
SOURCES = ("comps", "thewatchapi", "ebay")


def make_provider(settings: Settings) -> PriceProvider | ValuationService | None:
    source = settings.price_source
    has_ebay = bool(settings.ebay_client_id and settings.ebay_client_secret)
    if source == "auto":
        source = ("comps" if settings.apify_token else "thewatchapi" if settings.watchapi_token
                  else "ebay" if has_ebay else "")
    if source == "comps" and settings.apify_token:
        client = ApifyClient(settings.apify_token)
        return ValuationService([ApifyEbaySoldSource(client), ApifyChrono24Source(client)])
    if source == "thewatchapi" and settings.watchapi_token:
        return TheWatchApiProvider(settings.watchapi_token)
    if source == "ebay" and has_ebay:
        return EbayBrowseProvider(settings.ebay_client_id, settings.ebay_client_secret)
    if source not in ("", *SOURCES):
        log.warning("unknown PRICE_SOURCE %r (use auto, comps, thewatchapi or ebay)", settings.price_source)
    else:
        log.warning("no price source key set (APIFY_TOKEN, THEWATCHAPI_TOKEN or EBAY_CLIENT_ID/SECRET);"
                    " prices will not update")
    return None
