"""Chooses which comparables describe the owner's watch closely enough, and trims outliers."""
from statistics import median, quantiles

from .models import Comparable, WatchQuery
from .parse import norm, reference_matches

MIN_TIER_COUNT = 5
MIN_PER_SOURCE = 5  # a detail-matched tier must keep this many of each well-covered source
YEAR_WINDOW = 3
MIN_SPREAD = 0.06  # IQR floor, as a share of the median
DETAIL_FIELDS = ("dial", "bracelet", "metal")


def _brand_model_match(c: Comparable, q: WatchQuery) -> bool:
    text = norm(f"{c.title} {c.reference or ''}")
    words = [norm(w) for w in q.model.split() if norm(w)]
    return norm(q.brand) in text and all(w in text for w in words)


def _base_match(c: Comparable, q: WatchQuery) -> bool:
    return reference_matches(q.reference, c.title, c.reference) if q.reference else _brand_model_match(c, q)


def _details_match(c: Comparable, q: WatchQuery) -> bool:
    """Every detail the owner set must match; a listing that doesn't mention it is neutral."""
    return all(getattr(c, f) is None or getattr(c, f) == getattr(q, f) for f in DETAIL_FIELDS if getattr(q, f))


def in_tier(c: Comparable, q: WatchQuery, tier: int) -> bool:
    if tier == 1:
        return _base_match(c, q) and _details_match(c, q)
    if tier == 2:
        return _base_match(c, q)
    return _base_match(c, q) or _brand_model_match(c, q)


def prefer_year(comps: list[Comparable], q: WatchQuery) -> list[Comparable]:
    """With a year set, drop listings more than 3 years away (unknown years stay) if enough remain."""
    if q.year is None:
        return comps
    close = [c for c in comps if c.year is None or abs(c.year - q.year) <= YEAR_WINDOW]
    return close if len(close) >= MIN_TIER_COUNT else comps


def _keeps_sources(narrow: list[Comparable], wide: list[Comparable]) -> bool:
    """False when narrowing (e.g. to one dial color) leaves too few of a source the wider tier covers well."""
    for source in {c.source for c in wide}:
        in_wide = sum(c.source == source for c in wide)
        in_narrow = sum(c.source == source for c in narrow)
        if in_wide >= MIN_PER_SOURCE and in_narrow < MIN_PER_SOURCE:
            return False
    return True


def select_tier(comps: list[Comparable], q: WatchQuery) -> tuple[int, list[Comparable]]:
    tiers = {t: prefer_year([c for c in comps if in_tier(c, q, t)], q) for t in (1, 2, 3)}
    best: tuple[int, list[Comparable]] = (3, [])
    for tier in (1, 2, 3):
        chosen = tiers[tier]
        # tier 1 only wins if it doesn't throw away most of a source; the engine then adjusts for the detail
        if len(chosen) >= MIN_TIER_COUNT and (tier != 1 or _keeps_sources(chosen, tiers[2])):
            return tier, chosen
        if len(chosen) > len(best[1]):
            best = (tier, chosen)
    return best


def iqr_mask(values: list[float]) -> list[bool]:
    """True for each value inside [Q1 - 1.5 IQR, Q3 + 1.5 IQR]; with fewer than 4 values all are kept."""
    if len(values) < 4:
        return [True] * len(values)
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    spread = max(q3 - q1, MIN_SPREAD * median(values))  # tied prices must not collapse the sample
    low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
    return [low <= v <= high for v in values]


def trim_iqr(values: list[float]) -> list[float]:
    return [v for v, keep in zip(values, iqr_mask(values)) if keep]
