from watchbox.pricing import PriceResult, filter_listings, is_junk, listing_matches, summarize_prices


def test_is_junk_flags_accessory_listings():
    assert is_junk("Rolex Submariner 126610LN BOX ONLY")
    assert is_junk("Homage Submariner 126610LN style automatic")
    assert is_junk("Rolex 126610LN bezel insert black")


def test_is_junk_keeps_normal_titles():
    assert not is_junk("Rolex Submariner Date 126610LN Black Ceramic Bezel 2023")
    assert not is_junk("Rolex 126610LN Oyster bracelet full set")


def test_listing_matches_reference_ignoring_spacing_and_case():
    assert listing_matches("Rolex Submariner 126610 LN 2022", "126610LN")
    assert listing_matches("omega speedmaster 310.30.42.50.01.001", "310304250 01001")
    assert not listing_matches("Rolex Submariner 124060", "126610LN")


def test_filter_listings_keeps_matching_non_junk_prices():
    listings = [
        ("Rolex Submariner 126610 LN 2022", 13000.0),
        ("Rolex Submariner 124060", 9500.0),
        ("Rolex 126610LN box only", 900.0),
    ]
    assert filter_listings(listings, "126610LN") == [13000.0]


def test_summarize_returns_median_after_outlier_removal():
    prices = [12000.0, 13000.0, 13500.0, 14000.0, 60000.0, 1000.0]
    listings = [(f"Rolex 126610LN #{i}", p) for i, p in enumerate(prices)]
    # median of all six = 13250 -> keep [6625, 26500] -> 12000, 13000, 13500, 14000 -> median 13250
    assert summarize_prices(listings, "126610LN", "ebay") == PriceResult(price_usd=13250.0, sample_size=4, source="ebay")


def test_summarize_needs_at_least_three_listings():
    listings = [("Rolex 126610LN", 13000.0), ("Rolex 126610LN", 13500.0)]
    assert summarize_prices(listings, "126610LN", "ebay") is None
