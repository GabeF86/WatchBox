from watchbox.valuation.models import CONDITIONS, Comparable, Valuation, WatchQuery, label


def test_label_reads_naturally():
    assert label("very_good") == "Very good"
    assert label("new") == "New / unworn"
    assert label("full_set") == "Full set (box & papers)"
    assert label("two_tone") == "Two-tone"


def test_query_defaults_to_baseline_watch():
    q = WatchQuery(brand="Rolex", model="Submariner Date")
    assert (q.reference, q.condition, q.box_papers, q.dial) == ("", "excellent", "full_set", None)
    assert CONDITIONS[0] == "new"


def test_comparable_and_valuation_construct():
    c = Comparable(source="ebay", kind="sold", price_usd=11500.0, date=None, title="Rolex 116610LN")
    assert c.best_offer is False and c.box_papers is None
    v = Valuation(estimate_usd=11500.0, confidence="high", tier=1, n_ebay=20, n_c24=8, ebay_median=11500.0,
                  ebay_p10=10500.0, ebay_p90=12900.0, ebay_min=9800.0, ebay_max=13300.0, c24_median=12400.0,
                  gap=0.07, w_ebay=0.7, w_c24=0.3, backtest_n=20, backtest_mdape=0.04, backtest_within10=0.9,
                  factors={})
    assert v.failed_sources == ()
