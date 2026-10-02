"""Shared types and vocabularies for the valuation engine."""
from dataclasses import dataclass, field
from datetime import date

CONDITIONS = ("new", "excellent", "very_good", "good", "fair")
BOX_PAPERS = ("full_set", "box_only", "papers_only", "watch_only")
DIALS = ("black", "blue", "white", "silver", "green", "grey", "champagne", "brown", "red", "other")
BRACELETS = ("oyster", "jubilee", "president", "leather", "rubber", "nato", "other")
METALS = ("steel", "yellow_gold", "white_gold", "rose_gold", "two_tone", "platinum", "titanium", "other")

_LABELS = {
    "new": "New / unworn",
    "full_set": "Full set (box & papers)",
    "two_tone": "Two-tone",
    "nato": "NATO",
}


def label(value: str) -> str:
    return _LABELS.get(value, value.replace("_", " ").capitalize())


@dataclass(frozen=True)
class WatchQuery:
    brand: str
    model: str
    reference: str = ""
    year: int | None = None
    condition: str = "excellent"
    box_papers: str = "full_set"
    dial: str | None = None
    bracelet: str | None = None
    metal: str | None = None


@dataclass(frozen=True)
class Comparable:
    source: str  # "ebay" | "chrono24"
    kind: str  # "sold" | "asking"
    price_usd: float
    date: date | None
    title: str
    url: str = ""
    reference: str | None = None
    year: int | None = None
    condition: str | None = None
    box_papers: str | None = None
    dial: str | None = None
    bracelet: str | None = None
    metal: str | None = None
    best_offer: bool = False  # eBay "best offer accepted": the real sale price is unknown


@dataclass
class Valuation:
    estimate_usd: float
    confidence: str  # "high" | "medium" | "low"
    tier: int
    n_ebay: int
    n_c24: int
    ebay_median: float | None
    ebay_p10: float | None
    ebay_p90: float | None
    ebay_min: float | None
    ebay_max: float | None
    c24_median: float | None
    gap: float
    w_ebay: float
    w_c24: float
    backtest_n: int
    backtest_mdape: float | None
    backtest_within10: float | None
    factors: dict
    failed_sources: tuple[str, ...] = field(default=())
