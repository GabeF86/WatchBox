"""Turns comparables into one valuation for a watch. Pure: no network, no database."""
from statistics import median

from .adjust import adjust_price, learn_factors
from .backtest import backtest
from .blend import asking_gap, confidence, percentile, weights
from .match import select_tier, trim_iqr
from .models import Comparable, Valuation, WatchQuery
from .parse import is_junk


def value(query: WatchQuery, comps: list[Comparable], estimated_reference: bool = False,
          failed_sources: tuple[str, ...] = ()) -> Valuation | None:
    usable = [c for c in comps if c.price_usd > 0 and not is_junk(c.title, query.reference)]
    tier, chosen = select_tier(usable, query)
    if not chosen:
        return None
    factors = learn_factors(chosen)
    ebay = [c for c in chosen if c.source == "ebay" and c.kind == "sold" and not c.best_offer]
    c24 = [c for c in chosen if c.source == "chrono24"]

    ebay_adj = trim_iqr([adjust_price(c, factors, query) for c in ebay])
    c24_adj = trim_iqr([adjust_price(c, factors, query) for c in c24])
    gap = asking_gap([factors.to_baseline(c) for c in ebay], [factors.to_baseline(c) for c in c24])
    w_ebay, w_c24 = weights(len(ebay_adj), len(c24_adj))
    if w_ebay + w_c24 == 0:
        return None
    ebay_est = median(ebay_adj) if ebay_adj else 0.0
    c24_est = median(c24_adj) * (1 - gap) if c24_adj else 0.0
    estimate = round((w_ebay * ebay_est + w_c24 * c24_est) / 10) * 10

    combined = ebay_adj + [p * (1 - gap) for p in c24_adj]
    mid = median(combined)
    spread = (percentile(combined, 90) - percentile(combined, 10)) / mid if mid else 1.0
    bt_n, bt_mdape, bt_within = backtest(ebay, factors)

    ebay_raw = trim_iqr([c.price_usd for c in ebay])  # shown to the owner as-is, before adjustments
    c24_raw = trim_iqr([c.price_usd for c in c24])
    return Valuation(
        estimate_usd=float(estimate),
        confidence=confidence(tier, len(combined), spread, bt_mdape, estimated_reference, bool(failed_sources)),
        tier=tier, n_ebay=len(ebay_adj), n_c24=len(c24_adj),
        ebay_median=median(ebay_raw) if ebay_raw else None,
        ebay_p10=percentile(ebay_raw, 10) if ebay_raw else None,
        ebay_p90=percentile(ebay_raw, 90) if ebay_raw else None,
        ebay_min=min(ebay_raw) if ebay_raw else None,
        ebay_max=max(ebay_raw) if ebay_raw else None,
        c24_median=median(c24_raw) if c24_raw else None,
        gap=round(gap, 4), w_ebay=round(w_ebay, 3), w_c24=round(w_c24, 3),
        backtest_n=bt_n, backtest_mdape=bt_mdape, backtest_within10=bt_within,
        factors={"box": factors.box, "condition": factors.condition, "learned": factors.learned},
        failed_sources=tuple(failed_sources),
    )
