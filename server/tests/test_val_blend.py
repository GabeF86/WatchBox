import pytest

from watchbox.valuation.adjust import BOX_PRIOR, COND_PRIOR, Factors
from watchbox.valuation.backtest import backtest
from watchbox.valuation.blend import asking_gap, confidence, percentile, weights
from watchbox.valuation.models import Comparable

PRIORS = Factors(dict(BOX_PRIOR), dict(COND_PRIOR), {})


def sold(price):
    return Comparable(source="ebay", kind="sold", price_usd=price, date=None, title="Rolex 116610LN")


def test_percentile_interpolates():
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([0, 10], 10) == pytest.approx(1.0)
    assert percentile([5], 90) == 5


def test_asking_gap():
    assert asking_gap([100] * 5, [110] * 5) == pytest.approx((5 * (1 - 100 / 110) + 10 * 0.07) / 15)
    assert asking_gap([100] * 4, [110] * 5) == 0.07  # too little data
    assert asking_gap([130] * 5, [100] * 5) == 0.0  # measured -0.3 shrinks to (5*-0.3+0.7)/15 < 0
    assert asking_gap([50] * 5, [100] * 5) == 0.20  # (2.5+0.7)/15 = 0.2133, clamped


def test_weights():
    assert weights(10, 10) == pytest.approx((0.7, 0.3))
    assert weights(5, 10) == pytest.approx((0.35 / 0.65, 0.3 / 0.65))
    assert weights(0, 4) == (0.0, 1.0)
    assert weights(0, 0) == (0.0, 0.0)


@pytest.mark.parametrize("args, expected", [
    ((1, 12, 0.20, 0.05, False, False), "high"),
    ((1, 12, 0.20, 0.09, False, False), "medium"),
    ((3, 12, 0.20, None, False, False), "medium"),
    ((1, 4, 0.10, None, False, False), "low"),
    ((1, 12, 0.50, None, False, False), "low"),
    ((1, 12, 0.20, 0.05, True, False), "medium"),
    ((1, 12, 0.20, 0.05, False, True), "medium"),
    ((1, 6, 0.30, None, False, True), "low"),
])
def test_confidence(args, expected):
    assert confidence(*args) == expected


def test_confidence_caps():
    assert confidence(1, 12, 0.20, 0.05, False, False, sold_data=False) == "medium"
    assert confidence(1, 12, 0.20, 0.05, False, False, loose_match=True) == "low"
    assert confidence(1, 12, 0.20, 0.05, False, False, sold_data=True, loose_match=False) == "high"


def test_backtest_needs_six_sales():
    assert backtest([sold(10000.0)] * 5, PRIORS) == (0, None, None)


def test_backtest_identical_prices_are_perfect():
    assert backtest([sold(10000.0)] * 6, PRIORS) == (6, 0.0, 1.0)


def test_backtest_reports_known_error():
    n, mdape, within10 = backtest([sold(100.0)] * 5 + [sold(150.0)], PRIORS)
    assert n == 6 and mdape == 0.0 and within10 == pytest.approx(5 / 6)



def test_widened_match_caps_confidence_at_medium():
    assert confidence(1, 30, 0.10, 0.03, False, False, widened=True) == "medium"


def test_backtest_applies_detail_multiplier():
    blue = [Comparable(source="ebay", kind="sold", price_usd=11000.0, date=None, title="x", dial="blue")] * 3
    black = [Comparable(source="ebay", kind="sold", price_usd=10000.0, date=None, title="x", dial="black")] * 3
    m = lambda c: 1.1 if c.dial == "black" else 1.0  # noqa: E731
    n, mdape, within10 = backtest(blue + black, PRIORS, multiplier=m)
    assert n == 6 and mdape == pytest.approx(0.0)
