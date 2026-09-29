"""Picks the price provider from settings (PRICE_SOURCE=auto prefers TheWatchAPI, then eBay)."""
import logging

from .config import Settings
from .ebay import EbayBrowseProvider
from .pricing import PriceProvider
from .watchapi import TheWatchApiProvider

log = logging.getLogger("watchbox.providers")


def make_provider(settings: Settings) -> PriceProvider | None:
    source = settings.price_source
    has_ebay = bool(settings.ebay_client_id and settings.ebay_client_secret)
    if source == "auto":
        source = "thewatchapi" if settings.watchapi_token else "ebay" if has_ebay else ""
    if source == "thewatchapi" and settings.watchapi_token:
        return TheWatchApiProvider(settings.watchapi_token)
    if source == "ebay" and has_ebay:
        return EbayBrowseProvider(settings.ebay_client_id, settings.ebay_client_secret)
    if source not in ("", "thewatchapi", "ebay"):
        log.warning("unknown PRICE_SOURCE %r (use auto, thewatchapi or ebay)", settings.price_source)
    else:
        log.warning("no price source key set (THEWATCHAPI_TOKEN or EBAY_CLIENT_ID/SECRET); prices will not update")
    return None
