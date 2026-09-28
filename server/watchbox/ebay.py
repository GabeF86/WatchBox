"""eBay Browse API price provider (median asking price of current listings)."""
import base64
import time
from typing import Callable

import httpx

from .pricing import PriceResult, summarize_prices

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
WRISTWATCHES_CATEGORY = "31387"
SEARCH_FILTER = "buyingOptions:{FIXED_PRICE},price:[500..],priceCurrency:USD"


class EbayError(Exception):
    pass


class EbayBrowseProvider:
    source = "ebay"

    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15)
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def _get_token(self) -> str:
        if self._token and self._clock() < self._expires_at - 60:
            return self._token
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        response = self._http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        if response.status_code != 200:
            raise EbayError(f"token request failed: {response.status_code} {response.text[:200]}")
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = self._clock() + body["expires_in"]
        return self._token

    def search(self, brand: str, reference: str) -> list[tuple[str, float]]:
        response = self._http.get(
            SEARCH_URL,
            params={
                "q": f"{brand} {reference}",
                "category_ids": WRISTWATCHES_CATEGORY,
                "filter": SEARCH_FILTER,
                "limit": "100",
            },
            headers={"Authorization": f"Bearer {self._get_token()}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        )
        if response.status_code != 200:
            if response.status_code == 401:
                self._token = None
            raise EbayError(f"search failed: {response.status_code} {response.text[:200]}")
        listings = []
        for item in response.json().get("itemSummaries", []):
            price = item.get("price", {})
            converted_from = price.get("convertedFromCurrency")
            if converted_from and converted_from != "USD":
                continue
            if price.get("currency") == "USD" and "value" in price:
                listings.append((item.get("title", ""), float(price["value"])))
        return listings

    def get_price(self, brand: str, reference: str) -> PriceResult | None:
        return summarize_prices(self.search(brand, reference), reference, self.source)
