from watchbox.valuation.match import in_tier, prefer_year, select_tier, trim_iqr
from watchbox.valuation.models import Comparable, WatchQuery

Q = WatchQuery(brand="Rolex", model="Submariner Date", reference="116610LN", dial="black")


def comp(title="Rolex Submariner Date 116610LN", **kw):
    return Comparable(source=kw.pop("source", "ebay"), kind="sold", price_usd=kw.pop("price", 11000.0), date=None,
                      title=title, **kw)


def test_tier_rules():
    neutral = comp()  # no dial mentioned counts as neutral
    blue = comp(dial="blue")
    other_ref = comp("Rolex Submariner Date 126610LN")
    assert in_tier(neutral, Q, 1) and in_tier(comp(dial="black"), Q, 1)
    assert not in_tier(blue, Q, 1) and in_tier(blue, Q, 2)
    assert not in_tier(other_ref, Q, 2) and in_tier(other_ref, Q, 3)


def test_no_reference_uses_brand_and_model():
    q = WatchQuery(brand="Glashütte Original", model="Sixties Panorama Date")
    c = comp("Glashutte Original Sixties Panorama Date 2023")
    assert in_tier(c, q, 1) and in_tier(c, q, 3)
    assert not in_tier(comp("Glashutte Original Senator"), q, 3)


def test_select_tier_takes_tightest_with_five():
    comps = [comp(dial="black")] * 3 + [comp(dial="blue")] * 3
    tier, chosen = select_tier(comps, Q)
    assert tier == 2 and len(chosen) == 6


def test_select_tier_falls_back_to_largest_and_handles_empty():
    tier, chosen = select_tier([comp(dial="black")] * 2, Q)
    assert len(chosen) == 2
    assert select_tier([], Q) == (3, [])


def test_prefer_year_keeps_close_years_when_enough():
    q = WatchQuery(brand="Rolex", model="Submariner Date", reference="116610LN", year=2015)
    comps = [comp(year=y) for y in (2014, 2016, None, 2012, 2013, 2015, 2020, 2021)]
    assert sorted((c.year or 0) for c in prefer_year(comps, q)) == [0, 2012, 2013, 2014, 2015, 2016]
    assert len(prefer_year(comps[:4], q)) == 4  # too few close ones: keep everything


def test_trim_iqr():
    assert trim_iqr([10, 11, 12, 13, 100]) == [10, 11, 12, 13]
    assert trim_iqr([10, 100, 1000]) == [10, 100, 1000]


def test_trim_iqr_has_minimum_width_so_ties_do_not_collapse():
    assert len(trim_iqr([100] * 6 + [99, 101])) == 8
    assert len(trim_iqr([11500] * 7 + [11000, 12000, 12400])) == 10


def test_tier_3_is_superset_of_tier_2():
    assert in_tier(comp("Rolex Submariner 116610LN"), Q, 3)  # no "Date", but the reference matches


def test_iqr_mask_matches_trim_iqr():
    from watchbox.valuation.match import iqr_mask
    assert iqr_mask([10, 11, 12, 13, 100]) == [True, True, True, True, False]
    assert iqr_mask([10, 100, 1000]) == [True, True, True]
