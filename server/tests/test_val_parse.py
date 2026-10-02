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
    ("Customer favorite Rolex 116610LN", False),
])
def test_is_junk(title, junk):
    assert is_junk(title) is junk


def test_reference_matches_any_text_ignoring_spacing():
    assert reference_matches("116610LN", "2015 116610LN Rolex Submariner like new")
    assert reference_matches("116610LN", "Rolex Submariner Date", "116610 LN")
    assert not reference_matches("116610LN", "Rolex Submariner Date", "126610LN")
    assert not reference_matches("", "anything")


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
])
def test_condition_from_title(title, expected):
    assert condition_from_title(title) == expected


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
    ("Like new & unworn", False, "new"),
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
