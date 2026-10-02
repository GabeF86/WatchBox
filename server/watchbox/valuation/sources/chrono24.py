"""Chrono24 asking prices, with full listing details, via the memo23 Chrono24 scraper on Apify."""
from datetime import date
from urllib.parse import urlencode

from ..models import Comparable, WatchQuery
from ..parse import (box_papers_from_c24, bracelet_from_c24, condition_from_c24, dial_from_c24, metal_from_c24,
                     parse_title, year_from_text)
from .apify import ApifyClient

ACTOR = "memo23/chrono24-scraper"


def search_url(q: WatchQuery) -> str:
    query = f"{q.brand} {q.reference}" if q.reference else f"{q.brand} {q.model}"
    return "https://www.chrono24.com/search/index.htm?" + urlencode(
        {"query": query, "dosearch": "true", "currencyId": "USD"})


def comparable_from_row(row: dict) -> Comparable | None:
    price = row.get("price")
    if not isinstance(price, (int, float)) or price <= 0 or row.get("currency") != "USD":
        return None
    title = " ".join(p for p in (row.get("title"), row.get("subtitle")) if p)
    guessed = parse_title(title)
    scraped = row.get("scrapedAt")
    return Comparable(
        source="chrono24", kind="asking", price_usd=float(price),
        date=date.fromisoformat(scraped[:10]) if scraped else None,
        title=title, url=row.get("listingUrl") or "",
        reference=row.get("specs_referencenumber") or row.get("referenceNumber"),
        year=year_from_text(row.get("specs_year")) or guessed["year"],
        condition=condition_from_c24(row.get("specs_condition"), row.get("conditionNew") is True) or guessed["condition"],
        box_papers=box_papers_from_c24(row.get("scopeOfDelivery"), row.get("specs_scopeofdelivery"))
        or guessed["box_papers"],
        dial=dial_from_c24(row.get("specs_dialcolor")) or guessed["dial"],
        bracelet=bracelet_from_c24(row.get("specs_braceletmaterial")) or guessed["bracelet"],
        metal=metal_from_c24(row.get("specs_casematerial")) or guessed["metal"],
    )


class ApifyChrono24Source:
    name = "chrono24"

    def __init__(self, client: ApifyClient):
        self._client = client

    def payload(self, q: WatchQuery) -> dict:
        return {"startUrls": [search_url(q)], "fetchListingDetails": True, "maxIndexPages": 1, "maxItems": 40}

    def fetch(self, q: WatchQuery) -> list[Comparable]:
        rows = self._client.run(ACTOR, self.payload(q))
        return [c for c in map(comparable_from_row, rows) if c is not None]
