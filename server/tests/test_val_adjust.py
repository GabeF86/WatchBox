import pytest

from watchbox.valuation.adjust import BOX_PRIOR, COND_PRIOR, Factors, adjust_price, learn_factors
from watchbox.valuation.models import Comparable, WatchQuery


def comp(price, box_papers=None, condition=None, source="ebay"):
    return Comparable(source=source, kind="sold", price_usd=price, date=None, title="Rolex 116610LN",
                      box_papers=box_papers, condition=condition)


def test_prior_factors_and_unknowns():
    f = Factors(dict(BOX_PRIOR), dict(COND_PRIOR), {})
    assert f.factor("watch_only", "good") == pytest.approx(0.85 * 0.90)
    assert f.factor(None, None) == 1.0


def test_adjust_price_goes_through_baseline():
    f = Factors(dict(BOX_PRIOR), dict(COND_PRIOR), {})
    q = WatchQuery(brand="Rolex", model="Submariner", box_papers="full_set", condition="excellent")
    assert adjust_price(comp(8500.0, box_papers="watch_only"), f, q) == pytest.approx(10000.0)
    q_watch_only = WatchQuery(brand="Rolex", model="Submariner", box_papers="watch_only")
    assert adjust_price(comp(10000.0, box_papers="full_set"), f, q_watch_only) == pytest.approx(8500.0)


def test_learned_factor_shrinks_toward_prior():
    comps = [comp(10000.0, "full_set")] * 5 + [comp(8000.0, "watch_only")] * 5
    f = learn_factors(comps)
    assert f.box["watch_only"] == pytest.approx((5 * 0.8 + 10 * 0.85) / 15)
    assert f.learned["box:watch_only"] == pytest.approx(0.8)


def test_learned_factor_is_clamped_and_needs_enough_data():
    comps = [comp(10000.0, "full_set")] * 5 + [comp(5000.0, "watch_only")] * 5
    assert learn_factors(comps).box["watch_only"] == pytest.approx(0.75)  # prior 0.85 - 0.10
    few = [comp(10000.0, "full_set")] * 5 + [comp(8000.0, "watch_only")] * 2
    assert learn_factors(few).box["watch_only"] == BOX_PRIOR["watch_only"]
