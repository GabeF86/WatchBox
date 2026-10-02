import json
from pathlib import Path

import pytest

from watchbox.valuation.engine import value
from watchbox.valuation.models import Comparable, WatchQuery
from watchbox.valuation.sources import chrono24, ebay_sold

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def real_comps():
    ebay = [ebay_sold.comparable_from_row(r) for r in json.loads((FIXTURES / "ebay_sold_116610ln.json").read_text())]
    c24 = [chrono24.comparable_from_row(r) for r in json.loads((FIXTURES / "chrono24_116610ln.json").read_text())]
    return [c for c in ebay + c24 if c is not None]


SUB = WatchQuery(brand="Rolex", model="Submariner Date", reference="116610LN", dial="black", metal="steel")


def comp(price, source="ebay", **kw):
    kind = "sold" if source == "ebay" else "asking"
    return Comparable(source=source, kind=kind, price_usd=price, date=None, title=kw.pop("title", "Rolex 116610LN"),
                      **kw)


def test_real_submariner_data_gives_a_sensible_estimate(real_comps):
    v = value(SUB, real_comps)
    assert 10_500 <= v.estimate_usd <= 13_500
    assert v.tier == 1
    assert v.n_ebay >= 15 and v.n_c24 >= 5
    assert v.confidence in ("medium", "high")
    assert v.backtest_n >= 6 and v.backtest_mdape < 0.15
    assert v.ebay_p10 <= v.ebay_median <= v.ebay_p90


def test_watch_only_is_valued_below_full_set(real_comps):
    full = value(SUB, real_comps).estimate_usd
    bare = value(WatchQuery(brand="Rolex", model="Submariner Date", reference="116610LN",
                            box_papers="watch_only"), real_comps).estimate_usd
    assert bare < full


def test_chrono24_only_is_discounted_by_default_gap():
    v = value(SUB, [comp(10000.0, source="chrono24") for _ in range(6)])
    assert (v.w_ebay, v.w_c24) == (0.0, 1.0)
    assert v.estimate_usd == 9300.0  # 10000 × (1 − 0.07)


def test_no_usable_comparables_returns_none():
    assert value(SUB, []) is None
    assert value(SUB, [comp(10000.0, title="Rolex 116610LN box only")]) is None


def test_best_offer_sales_are_left_out_of_ebay_figures():
    comps = [comp(10000.0) for _ in range(6)] + [comp(20000.0, best_offer=True)]
    v = value(SUB, comps)
    assert v.n_ebay == 6 and v.ebay_max == 10000.0


def test_failed_source_lowers_confidence():
    comps = [comp(10000.0 + i) for i in range(12)]
    assert value(SUB, comps).confidence == "high"
    assert value(SUB, comps, failed_sources=("chrono24",)).confidence == "medium"
    assert value(SUB, comps, estimated_reference=True).confidence == "medium"


def test_best_offer_sales_do_not_drive_tier_selection():
    t1 = [comp(10000.0, best_offer=True, dial="black") for _ in range(5)] + [comp(10000.0, dial="black")]
    t2 = [comp(10000.0 + i, dial="white") for i in range(6)]
    v = value(SUB, t1 + t2)
    assert v.tier == 2 and v.n_ebay >= 6


def test_adjusted_outlier_is_dropped_from_counts_and_stats():
    comps = [comp(10000.0 + 10 * i) for i in range(8)] + [comp(30000.0)]
    v = value(SUB, comps)
    assert v.n_ebay == 8 and v.ebay_max == 10070.0


def test_real_data_counts_match_stats(real_comps):
    v = value(SUB, real_comps)
    assert v.ebay_min <= v.ebay_median <= v.ebay_max and v.n_ebay == 24 and v.n_c24 == 11


def test_chrono24_only_confidence_is_capped_at_medium():
    v = value(SUB, [comp(10000.0 + i, source="chrono24") for i in range(12)])
    assert v.confidence in ("low", "medium")


def test_tier3_with_reference_is_low_confidence():
    comps = [comp(11000.0 + i, title="Rolex Submariner Date 2015") for i in range(6)]
    v = value(SUB, comps)
    assert v.tier == 3 and v.confidence == "low"


def test_fewer_than_three_comparables_returns_none():
    assert value(SUB, [comp(10000.0), comp(10100.0)]) is None


def test_estimate_rounds_half_up():
    v = value(SUB, [comp(10005.0) for _ in range(6)])
    assert v.estimate_usd == 10010.0
