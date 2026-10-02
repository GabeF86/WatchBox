"""eBay sold listings (last 90 days) via the memo23 eBay scraper on Apify."""
import re
from datetime import date, datetime

from ..models import Comparable, WatchQuery
from ..parse import parse_title
from .apify import ApifyClient

ACTOR = "memo23/ebay-search-scraper-ppe"
WRISTWATCHES = "31387"
SOLD_DATE_RE = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")


def ebay_query(q: WatchQuery) -> str:
    if q.reference:
        return f"{q.brand} {q.reference}"
    parts = [q.brand, q.model]
    if q.dial and q.dial != "other":
        parts.append(q.dial)
    return " ".join(parts)


def parse_sold_date(text: str | None) -> date | None:
    m = SOLD_DATE_RE.search(text or "")
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").date()


def comparable_from_row(row: dict) -> Comparable | None:
    if row.get("type") == "sold-price-summary":
        return None
    price = row.get("priceValue")
    if not isinstance(price, (int, float)) or price <= 0 or (row.get("currency") or "USD") != "USD":
        return None
    title = row.get("title") or ""
    return Comparable(source="ebay", kind="sold", price_usd=float(price), date=parse_sold_date(row.get("soldDate")),
                      title=title, url=row.get("url") or "", best_offer=bool(row.get("bestOfferAccepted")),
                      **parse_title(title))


class ApifyEbaySoldSource:
    name = "ebay"

    def __init__(self, client: ApifyClient):
        self._client = client

    def payload(self, q: WatchQuery) -> dict:
        return {"searchQuery": ebay_query(q), "marketplace": "ebay.com", "mode": "sold", "soldWithinDays": 90,
                "category": WRISTWATCHES, "maxItems": 60, "includeSummary": False, "detailedItems": False}

    def fetch(self, q: WatchQuery) -> list[Comparable]:
        rows = self._client.run(ACTOR, self.payload(q))
        return [c for c in map(comparable_from_row, rows) if c is not None]
