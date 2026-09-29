"""TheWatchAPI price provider (thewatchapi.com): latest indicative USD asking price per reference.

Their history can lag by months, so the date of the point used is kept (PriceResult.as_of).
"""
import logging
import re
import unicodedata

import httpx

from .pricing import PriceResult

PRICE_HISTORY_URL = "https://api.thewatchapi.com/v1/reference/price/history"

log = logging.getLogger("watchbox.watchapi")


class WatchApiError(Exception):
    pass


def _norm_brand(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


class TheWatchApiProvider:
    source = "thewatchapi"

    def __init__(self, api_token: str, http: httpx.Client | None = None):
        self._api_token = api_token
        self._http = http or httpx.Client(timeout=15)

    def price_history(self, reference: str) -> dict:
        # The token travels in the query string, so never put the URL or request in an error message.
        response = self._http.get(PRICE_HISTORY_URL, params={
            "api_token": self._api_token,
            "reference_number": reference,
        })
        if response.status_code != 200:
            try:
                error = response.json()["error"]
                detail = f"{error.get('code')}: {error.get('message')}"
            except (ValueError, KeyError, TypeError):
                detail = response.text[:200]
            if response.status_code in (402, 403):
                detail += " (price history may need a higher TheWatchAPI plan)"
            raise WatchApiError(f"price history failed: {response.status_code} {detail}")
        return response.json()

    def get_price(self, brand: str, reference: str) -> PriceResult | None:
        body = self.price_history(reference)
        api_brand = (body.get("meta") or {}).get("brand")
        if api_brand and _norm_brand(api_brand) != _norm_brand(brand):
            log.warning("reference %s belongs to %s, not %s", reference, api_brand, brand)
            return None
        points = [p for p in body.get("data") or [] if p.get("price") is not None]
        if not points:
            return None
        latest = max(points, key=lambda p: p["date"])
        return PriceResult(price_usd=round(float(latest["price"]), 2), sample_size=len(points), source=self.source,
                           as_of=latest["date"][:10])
