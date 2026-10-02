import pytest

from watchbox.valuation.parse import (
    box_papers_from_c24, box_papers_from_title, bracelet_from_c24, bracelet_from_title, condition_from_c24,
    condition_from_title, dial_from_c24, dial_from_title, is_junk, metal_from_c24, metal_from_title, norm,
    parse_title, reference_matches, year_from_text,
)


def test_norm_strips_punctuation_and_accents():
    assert norm("Glashütte Original") == "glashutteoriginal"
    assert norm("2-39-47-01-01-04") == "23947010104"


@pytest.mark.parametrize("title, junk", [
    ("Rolex Submariner Custom Green Dial And Bezel 116610LN Looks Si", True),
    ("Black PVD/DLC Coated Stainless Steel Watch", True),
    ("Rolex 116610LN box only", True),
    ("Rolex Submariner for parts or repair", True),
    ("Rolex Submariner Date 116610LN Black Ceramic Bezel", False),
    ("Rolex Submariner 116610LN Steel 116659SABR Natural Diamonds Sapphires", True),
    ("Rolex Datejust customized with diamonds", True),
    ("Rolex Datejust gem set bezel", True),
    ("Customer favorite Rolex 116610LN", False),
])
def test_is_junk(title, junk):
    assert is_junk(title) is junk


@pytest.mark.parametrize("title, reference, junk", [
    ("Rolex Datejust 126284RBR diamond bezel", "126284RBR", False),
    ("Rolex Submariner 116610LN Steel 116659SABR Natural Diamonds Sapphires", "116610LN", True),
    ("Rolex Datejust diamond dial", None, True),
    ("Rolex 126284RBR diamond bezel", "126284RBR-0011", False),
    ("Rolex Datejust 126284RBR box only", "126284RBR-0011", True),
    ("Rolex Datejust 126284RBR box only", "126284RBR", True),
    ("Rolex Datejust 126284RBR custom diamond bezel", "126284RBR", True),
])
def test_is_junk_allows_gems_only_on_gem_set_references(title, reference, junk):
    assert is_junk(title, reference) is junk


def test_reference_matches_any_text_ignoring_spacing():
    assert reference_matches("116610LN", "2015 116610LN Rolex Submariner like new")
    assert reference_matches("116610LN", "Rolex Submariner Date", "116610 LN")
    assert not reference_matches("116610LN", "Rolex Submariner Date", "126610LN")
    assert not reference_matches("", "anything")


@pytest.mark.parametrize("ref, text, expected", [
    ("16610LN", "Rolex 116610LN", False),
    ("1680", "Rolex 16800", False),
    ("116610LN", "Submariner 40 116610LN", True),
    ("116610LN", "Rolex 116610 LN", True),
    ("2-39-47-01-01-04", "Glash\u00fctte 2-39-47-01-01-04 Sixties", True),
])
def test_reference_matches_respects_digit_boundaries(ref, text, expected):
    assert reference_matches(ref, text) is expected


@pytest.mark.parametrize("text, year", [
    ("2015 116610LN Rolex Submariner", 2015),
    ("2014 (Approximation)", 2014),
    ("Unknown", None),
    ("Rolex Submariner 116610LN (40MM) ebay Live! 1/13/18", None),
    (None, None),
])
def test_year_from_text(text, year):
    assert year_from_text(text) == year


@pytest.mark.parametrize("title, expected", [
    ("eBay Live- Rolex Submariner Date 40mm 116610LN B&P 2014", "full_set"),
    ("EXCELLENT ROLEX Submariner 116610LN CARD & BOX SERVICED 2023!", "full_set"),
    ("#80 Rolex Submariner Date 40mm Black Dial 116610LN 2013 Papers", "papers_only"),
    ("116610LN With Box Steel 40mm Black Dial", "box_only"),
    ("Rolex 116610LN no box no papers", "watch_only"),
    ("2020 Rolex Submariner Date 116610LN 40mm Black Ceramic Stainless Steel Box Paper", "full_set"),
    ("Rolex Submariner Date 116610LN 40MM Black Oyster Steel Box Paper", "full_set"),
    ("Rolex 116610LN B+P", "full_set"),
    ("Rolex 116610LN no box no card", "watch_only"),
    ("Rolex 116610LN 1 year warranty, pay by credit card", None),
    ("Rolex 116610LN no box", "watch_only"),
    ("Rolex 116610LN with box, no papers", "box_only"),
    ("Rolex 116610LN no box, papers", "papers_only"),
    ("2018 CARD ROLEX MENS SUBMARINER DATE 116610LN CERAMIC 40MM BLACK STEEL WATCH", "papers_only"),
    ("Rolex 116610LN with warranty card", "papers_only"),
    ("ROLEX Stainless Steel 40mm Submariner 116610LN Box Warranty 2020 MINTY", "full_set"),
    ("Rolex 116610LN 2019 Warranty Card", "papers_only"),
    ("Rolex 116610LN warranty", "papers_only"),
    ("Rolex 116610LN 1 year warranty", None),
    ("Rolex 116610LN 2 yr warranty", None),
    ("Rolex 116610LN 5 year warranty 2020", "papers_only"),
    ("Rolex 116610LN 15 year warranty", None),
    ("Rolex 116610LN 5 month warranty", None),
    ("Rolex 116610LN 12 month warranty", None),
    ("Rolex 116610LN lifetime warranty", None),
    ("Rolex 116610LN pay by credit card or debit card", None),
    ("Rolex 116610LN box credit card accepted", "box_only"),
    ("2017 Rolex Submariner Date 116610LN Black Dial Oyster Bracelet", None),
])
def test_box_papers_from_title(title, expected):
    assert box_papers_from_title(title) == expected


@pytest.mark.parametrize("title, expected", [
    ("2015 116610LN Rolex Submariner like new", "excellent"),
    ("MINT Rolex Submariner Date", "excellent"),
    ("New Rolex Submariner 116610LN 40mm", "new"),
    ("Unworn Submariner NOS Full Stickers 114060", "new"),
    ("2017 Rolex Submariner Date 116610LN", None),
    ("Rolex 116610LN with new strap", None),
    ("Rolex 116610LN new service just done", None),
    ("Rolex 116610LN not new", None),
    ("New York dealer Rolex 116610LN", None),
    ("New strap Rolex 116610LN", None),
    ("Rolex 116610LN BNIB sealed", "new"),
    ("Rolex 116610LN brand new", "new"),
    ("Rolex 116610LN new old stock", "new"),
    ("Rolex 116610LN new with tags", "new"),
])
def test_condition_from_title(title, expected):
    assert condition_from_title(title) == expected


@pytest.mark.parametrize("text, year", [
    ("EXCELLENT ROLEX Submariner 116610LN CARD & BOX SERVICED 2023!", None),
    ("EXCELLENT ROLEX Submariner 116610LN BOX & CARD & 2023 SERVICE CARD!", None),
    ("Rolex 116610LN B&P 2015 + 2022 SC", 2015),
    ("Rolex 116610LN 2021 RSC", None),
    ("Rolex 116610LN polished 2019", None),
    ("Rolex 116610LN warranty 2024", 2024),
    ("ROLEX Stainless Steel 40mm Submariner 116610LN Box Warranty 2020 MINTY", 2020),
    ("Rolex 116610LN 2019 Warranty Card", 2019),
    ("Rolex 116610LN Serviced in 2022", None),
    ("2018 CARD ROLEX MENS SUBMARINER DATE 116610LN", 2018),
    ("Rolex Vintage 1960s Submariner", None),
    ("Rolex 116610LN 2099", None),
])
def test_year_ignores_service_years_decades_and_future(text, year):
    assert year_from_text(text) == year


def test_dial_bracelet_metal_from_title():
    assert dial_from_title("Rolex Submariner Date 40mm Black Dial 116610LN") == "black"
    assert dial_from_title("Rolex Datejust 41 126334 Grey dial") == "grey"
    assert dial_from_title("Rolex Submariner Black Ceramic Bezel") is None
    assert bracelet_from_title("Rolex Submariner Date 116610LN Black Dial Oyster Bracelet") == "oyster"
    assert bracelet_from_title("Rolex Datejust 41 Jubilee 126334") == "jubilee"
    assert bracelet_from_title("Rolex Oyster Perpetual 41") is None
    assert bracelet_from_title("Yacht-Master 42 Oysterflex") == "rubber"
    assert metal_from_title("Rolex Submariner Date 40mm Stainless Steel") == "steel"
    assert metal_from_title("Datejust 41 Rolesor White Gold Bezel") == "two_tone"
    assert metal_from_title("Daytona Everose Gold") == "rose_gold"
    assert metal_from_title("Day-Date 40 Yellow Gold") == "yellow_gold"
    assert metal_from_title("Rolex Submariner") is None


def test_parse_title_returns_all_detail_keys():
    assert parse_title("eBay Live- Rolex Submariner Date 40mm Black Dial 116610LN B&P 2014 Stainless Steel") == {
        "year": 2014, "condition": None, "box_papers": "full_set", "dial": "black", "bracelet": None, "metal": "steel",
    }


@pytest.mark.parametrize("text, new, expected", [
    ("Used (very good)", False, "very_good"),
    ("Used (good)", False, "good"),
    ("Like new & unworn", False, "excellent"),
    ("Like new & unworn", True, "new"),
    ("Unworn", False, "new"),
    ("Used (mint)", False, "excellent"),
    ("Used (fair)", False, "fair"),
    (None, True, "new"),
    (None, False, None),
])
def test_condition_from_c24(text, new, expected):
    assert condition_from_c24(text, new) == expected


@pytest.mark.parametrize("enum, text, expected", [
    ("WithBoxAndPapers", None, "full_set"),
    ("WithBox", None, "box_only"),
    ("WithPapers", None, "papers_only"),
    ("WatchOnly", None, "watch_only"),
    (None, "Original box, no original papers", "box_only"),
    (None, "No original box, original papers", "papers_only"),
    (None, "No original box, no original papers", "watch_only"),
    (None, None, None),
])
def test_box_papers_from_c24(enum, text, expected):
    assert box_papers_from_c24(enum, text) == expected


def test_c24_dial_bracelet_metal():
    assert dial_from_c24("Black") == "black"
    assert dial_from_c24("Gray") == "grey"
    assert dial_from_c24("Mother of pearl") == "other"
    assert dial_from_c24(None) is None
    assert bracelet_from_c24("Leather") == "leather"
    assert bracelet_from_c24("Rubber") == "rubber"
    assert bracelet_from_c24("Steel") is None
    assert metal_from_c24("Steel") == "steel"
    assert metal_from_c24("Gold/Steel") == "two_tone"
    assert metal_from_c24("Rose gold") == "rose_gold"
    assert metal_from_c24("Red gold") == "rose_gold"
    assert metal_from_c24("Yellow gold") == "yellow_gold"
    assert metal_from_c24("Ceramic") == "other"
    assert metal_from_c24(None) is None
