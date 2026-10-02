"""Turns comparables into one valuation for a watch. Pure: no network, no database."""
from statistics import median

from .adjust import DETAIL_FIELDS, adjust_price, detail_adjust, learn_detail_factors, learn_factors
from .backtest import backtest
from .blend import asking_gap, confidence, percentile, weights
from .match import in_tier, iqr_mask, prefer_year, select_tier
from .models import Comparable, Valuation, WatchQuery
from .parse import is_junk

MIN_COMPARABLES = 3
MIN_PER_SOURCE = 5  # below this, a source's exact-detail matches are too few to stand on their own


def _widen_thin_sources(usable, query, tier, chosen):
    """Tier 1 matches the owner's dial/bracelet. A source with fewer than MIN_PER_SOURCE such matches, but
    plenty of the same reference with other dials/bracelets, is widened to those, provided the detail's
    price effect can be measured. Other sources keep their exact matches. Metal is never relaxed."""
    if tier != 1 or not any(getattr(query, a) for a in DETAIL_FIELDS):
        return chosen, {}, []
    pool = prefer_year([c for c in usable if in_tier(c, query, 2)], query)
    detail = learn_detail_factors(pool, query, learn_factors(pool))
    widened = []
    for source in sorted({c.source for c in pool}):
        narrow = [c for c in chosen if c.source == source]
        wide = [c for c in pool if c.source == source]
        thinning = [a for a in DETAIL_FIELDS
                    if getattr(query, a) and any(getattr(c, a) not in (None, getattr(query, a)) for c in wide)]
        if len(narrow) < MIN_PER_SOURCE <= len(wide) and thinning and all(a in detail for a in thinning):
            chosen = [c for c in chosen if c.source != source] + wide
            widened.append(source)
    return chosen, (detail if widened else {}), widened


def _kept(comps: list[Comparable], adjusted: list[float]) -> tuple[list[Comparable], list[float]]:
    """Comparables whose adjusted price survives outlier trimming, with those adjusted prices."""
    mask = iqr_mask(adjusted)
    return [c for c, k in zip(comps, mask) if k], [a for a, k in zip(adjusted, mask) if k]


def value(query: WatchQuery, comps: list[Comparable], estimated_reference: bool = False,
          failed_sources: tuple[str, ...] = ()) -> Valuation | None:
    # best-offer sales hide the real price: leave them out before tiers and factors see them
    usable = [c for c in comps if c.price_usd > 0 and not c.best_offer and not is_junk(c.title, query.reference)]
    tier, chosen = select_tier(usable, query)
    if not chosen:
        return None
    chosen, detail, widened = _widen_thin_sources(usable, query, tier, chosen)
    factors = learn_factors(chosen)
    if tier >= 2:  # wider tiers mix dials/bracelets, so adjust for the difference where it can be measured
        detail = learn_detail_factors(chosen, query, factors)
    multiplier = lambda c: detail_adjust(c, query, detail)  # noqa: E731
    adjust = lambda c: adjust_price(c, factors, query) * multiplier(c)  # noqa: E731
    ebay_all = [c for c in chosen if c.source == "ebay" and c.kind == "sold"]
    c24_all = [c for c in chosen if c.source == "chrono24"]

    ebay, ebay_adj = _kept(ebay_all, [adjust(c) for c in ebay_all])
    c24, c24_adj = _kept(c24_all, [adjust(c) for c in c24_all])
    gap = asking_gap([factors.to_baseline(c) * multiplier(c) for c in ebay],
                     [factors.to_baseline(c) * multiplier(c) for c in c24])
    w_ebay, w_c24 = weights(len(ebay_adj), len(c24_adj))
    if w_ebay + w_c24 == 0:
        return None
    ebay_est = median(ebay_adj) if ebay_adj else 0.0
    c24_est = median(c24_adj) * (1 - gap) if c24_adj else 0.0
    estimate = int((w_ebay * ebay_est + w_c24 * c24_est) / 10 + 0.5) * 10

    combined = ebay_adj + [p * (1 - gap) for p in c24_adj]
    if len(combined) < MIN_COMPARABLES:
        return None
    mid = median(combined)
    spread = (percentile(combined, 90) - percentile(combined, 10)) / mid if mid else 1.0
    bt_n, bt_mdape, bt_within = backtest(ebay, factors, multiplier)

    ebay_raw = [c.price_usd for c in ebay]  # shown to the owner as-is, before adjustments
    c24_raw = [c.price_usd for c in c24]
    return Valuation(
        estimate_usd=float(estimate),
        confidence=confidence(tier, len(combined), spread, bt_mdape, estimated_reference, bool(failed_sources),
                              sold_data=bool(ebay), loose_match=tier == 3 and bool(query.reference),
                              widened=bool(widened) or (tier >= 2 and bool(detail))),
        tier=tier, n_ebay=len(ebay), n_c24=len(c24),
        ebay_median=median(ebay_raw) if ebay_raw else None,
        ebay_p10=percentile(ebay_raw, 10) if ebay_raw else None,
        ebay_p90=percentile(ebay_raw, 90) if ebay_raw else None,
        ebay_min=min(ebay_raw) if ebay_raw else None,
        ebay_max=max(ebay_raw) if ebay_raw else None,
        c24_median=median(c24_raw) if c24_raw else None,
        gap=round(gap, 4), w_ebay=round(w_ebay, 3), w_c24=round(w_c24, 3),
        backtest_n=bt_n, backtest_mdape=bt_mdape, backtest_within10=bt_within,
        factors={"box": factors.box, "condition": factors.condition, "learned": factors.learned,
                 "detail": detail, "widened": widened},
        failed_sources=tuple(failed_sources),
    )
