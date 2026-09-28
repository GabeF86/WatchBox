"""Price provider interface and the provider-independent price math."""
import re
from dataclasses import dataclass
from statistics import median
from typing import Protocol

MIN_SAMPLES = 3

JUNK_PHRASES = (
    "box only", "papers only", "empty box", "strap only", "bracelet only", "band only",
    "links only", "dial only", "bezel only", "bezel insert", "crown only", "case back",
    "for parts", "parts only", "repair", "homage", "replica", "manual", "booklet",
)


@dataclass(frozen=True)
class PriceResult:
    price_usd: float
    sample_size: int
    source: str


class PriceProvider(Protocol):
    def get_price(self, brand: str, reference: str) -> PriceResult | None: ...


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_junk(title: str) -> bool:
    lowered = title.lower()
    return any(phrase in lowered for phrase in JUNK_PHRASES)


def listing_matches(title: str, reference: str) -> bool:
    return _norm(reference) in _norm(title) and not is_junk(title)


def filter_listings(listings: list[tuple[str, float]], reference: str) -> list[float]:
    return [price for title, price in listings if listing_matches(title, reference)]


def summarize_prices(listings: list[tuple[str, float]], reference: str, source: str) -> PriceResult | None:
    prices = filter_listings(listings, reference)
    if len(prices) < MIN_SAMPLES:
        return None
    mid = median(prices)
    kept = [p for p in prices if 0.5 * mid <= p <= 2 * mid]
    if len(kept) < MIN_SAMPLES:
        return None
    return PriceResult(price_usd=round(median(kept), 2), sample_size=len(kept), source=source)
