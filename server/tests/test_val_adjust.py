import pytest

from watchbox.valuation.adjust import (BOX_PRIOR, COND_PRIOR, Factors, adjust_price, detail_adjust, learn_detail_factors,
                                       learn_factors)
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


def test_learned_factor_never_beats_the_better_level():
    comps = [comp(10000.0, "full_set")] * 5 + [comp(12000.0, "papers_only")] * 5
    assert learn_factors(comps).box["papers_only"] == 1.0  # shrunk 1.04 is capped at the baseline


def test_learned_factor_is_clamped_and_needs_enough_data():
    comps = [comp(10000.0, "full_set")] * 5 + [comp(5000.0, "watch_only")] * 5
    assert learn_factors(comps).box["watch_only"] == pytest.approx(0.75)  # prior 0.85 - 0.10
    few = [comp(10000.0, "full_set")] * 5 + [comp(8000.0, "watch_only")] * 2
    assert learn_factors(few).box["watch_only"] == BOX_PRIOR["watch_only"]


def dcomp(price, dial=None, bracelet=None, source="ebay"):
    return Comparable(source=source, kind="sold", price_usd=price, date=None, title="Rolex 126334",
                      dial=dial, bracelet=bracelet)


PRIORS = Factors(dict(BOX_PRIOR), dict(COND_PRIOR), {})
BLUE = WatchQuery(brand="Rolex", model="Datejust 41", reference="126334", dial="blue")


def test_detail_factor_measures_dial_premium_and_shrinks():
    comps = [dcomp(12000.0, "blue")] * 5 + [dcomp(10000.0, "black")] * 5
    assert learn_detail_factors(comps, BLUE, PRIORS)["dial"] == pytest.approx((5 * 1.2 + 10) / 15)


def test_detail_factor_needs_enough_data_and_is_clamped():
    assert learn_detail_factors([dcomp(12000.0, "blue")] * 2 + [dcomp(10000.0, "black")] * 5, BLUE, PRIORS) == {}
    big = [dcomp(30000.0, "blue")] * 5 + [dcomp(10000.0, "black")] * 5
    assert learn_detail_factors(big, BLUE, PRIORS)["dial"] == pytest.approx(1.20)


def test_detail_adjust_applies_only_to_listings_with_a_different_known_detail():
    detail = {"dial": 1.1}
    assert detail_adjust(dcomp(10000.0, "blue"), BLUE, detail) == 1.0
    assert detail_adjust(dcomp(10000.0, "black"), BLUE, detail) == pytest.approx(1.1)
    assert detail_adjust(dcomp(10000.0, None), BLUE, detail) == 1.0  # unknown is neutral, as in tier 1


def test_detail_factor_ignores_listings_with_unknown_detail():
    comps = [dcomp(12000.0, "blue")] * 5 + [dcomp(10000.0, "black")] * 5 + [dcomp(50000.0)] * 5
    assert learn_detail_factors(comps, BLUE, PRIORS)["dial"] == pytest.approx((5 * 1.2 + 10) / 15)
