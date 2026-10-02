"""Box & papers and condition adjustments: priors, nudged by what the watch's own listings show."""
from dataclasses import dataclass
from statistics import median
from typing import Callable

from .models import Comparable, WatchQuery

BOX_PRIOR = {"full_set": 1.00, "papers_only": 0.94, "box_only": 0.92, "watch_only": 0.85}
COND_PRIOR = {"new": 1.10, "excellent": 1.00, "very_good": 0.96, "good": 0.90, "fair": 0.80}
SHRINK = 10  # how many comparables a measured factor needs before it outweighs the prior
CLAMP = 0.10  # a learned factor stays within ±0.10 of its prior
MIN_GROUP = 3


@dataclass
class Factors:
    box: dict[str, float]
    condition: dict[str, float]
    learned: dict[str, float]  # raw measured ratios, for inspection

    def factor(self, box_papers: str | None, condition: str | None) -> float:
        box = self.box.get(box_papers, 1.0) if box_papers else 1.0
        cond = self.condition.get(condition, 1.0) if condition else 1.0
        return box * cond

    def to_baseline(self, c: Comparable) -> float:
        """The comparable's price as if it were a full set in excellent condition."""
        return c.price_usd / self.factor(c.box_papers, c.condition)


def adjust_price(c: Comparable, factors: Factors, q: WatchQuery) -> float:
    return factors.to_baseline(c) * factors.factor(q.box_papers, q.condition)


def _measured(comps, attr, value, baseline, other_factor: Callable[[Comparable], float]):
    """Median price ratio of `value` vs `baseline` within each source, pooled by count. None if too little data."""
    ratios = []
    for source in sorted({c.source for c in comps}):
        group = [c.price_usd / other_factor(c) for c in comps if c.source == source and getattr(c, attr) == value]
        base = [c.price_usd / other_factor(c) for c in comps if c.source == source and getattr(c, attr) == baseline]
        if len(group) >= MIN_GROUP and len(base) >= MIN_GROUP:
            ratios.append((median(group) / median(base), len(group)))
    if not ratios:
        return None
    n = sum(k for _, k in ratios)
    return sum(r * k for r, k in ratios) / n, n


def _shrink(measured: float, n: int, prior: float, lo: float | None = None, hi: float | None = None) -> float:
    """Shrink toward the prior, stay within ±CLAMP of it and within the optional [lo, hi] bounds."""
    blended = (n * measured + SHRINK * prior) / (n + SHRINK)
    value = min(max(blended, prior - CLAMP), prior + CLAMP)
    if lo is not None:
        value = max(value, lo)
    if hi is not None:
        value = min(value, hi)
    return value


def learn_factors(comps: list[Comparable]) -> Factors:
    box, cond, learned = dict(BOX_PRIOR), dict(COND_PRIOR), {}
    cond_prior = lambda c: COND_PRIOR.get(c.condition, 1.0) if c.condition else 1.0
    for value in BOX_PRIOR:
        if value == "full_set":
            continue
        m = _measured(comps, "box_papers", value, "full_set", cond_prior)
        if m:
            box[value] = _shrink(m[0], m[1], BOX_PRIOR[value], hi=1.0)  # never beats a full set
            learned[f"box:{value}"] = m[0]
    box_learned = lambda c: box.get(c.box_papers, 1.0) if c.box_papers else 1.0
    for value in COND_PRIOR:
        if value == "excellent":
            continue
        m = _measured(comps, "condition", value, "excellent", box_learned)
        if m:
            # "new" never ranks below excellent; every lower grade never ranks above it
            cond[value] = _shrink(m[0], m[1], COND_PRIOR[value], lo=1.0 if value == "new" else None,
                                  hi=None if value == "new" else 1.0)
            learned[f"condition:{value}"] = m[0]
    return Factors(box, cond, learned)
