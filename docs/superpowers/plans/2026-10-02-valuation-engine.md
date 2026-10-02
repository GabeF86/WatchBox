# Valuation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estimate each watch's resale value from eBay sold listings and Chrono24 asking prices, adjusted for its condition, box & papers, year, dial, bracelet and metal, with a confidence level backed by a leave-one-out backtest.

**Architecture:** A new package, `server/watchbox/valuation/`, holds:
- pure modules: `models`, `parse`, `match`, `adjust`, `blend`, `backtest` and `engine`;
- Apify-backed sources: `sources/`;
- `ValuationService`, which fetches comparables, stores them and values the watch.

It plugs into the existing app as a "provider" that has `refresh_watch` and `recompute` methods. `watchbox/refresh.py` delegates to it, and `db.py` stores comparables and valuations. The latest valuation becomes the watch's `price_usd`, so the LCD and web page keep working.

**Tech Stack:** Python 3.13, FastAPI, SQLite, httpx (`MockTransport` in tests), pytest. Apify actors `memo23/ebay-search-scraper-ppe` and `memo23/chrono24-scraper`.

**Spec:** `docs/superpowers/specs/2026-10-02-valuation-engine-design.md`

**Conventions:**
- Run commands from the repo root. Tests: `server/.venv/bin/pytest server/tests -q`.
- Every commit message ends with a blank line and then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Steps marked **[CONTROLLER]** make live paid API calls (a few cents of Apify credit) and are run by the coordinating session, not a subagent.

---

## File map

```
server/watchbox/valuation/
  __init__.py          (empty)
  models.py            vocabularies, label(), WatchQuery, Comparable, Valuation
  parse.py             norm, junk filter, reference match, title and Chrono24 field parsers
  match.py             tiers, year preference, IQR trimming
  adjust.py            box & papers and condition factors (priors and learned)
  blend.py             percentile, asking-to-sold gap, weights, confidence
  backtest.py          leave-one-out MdAPE
  engine.py            value(query, comparables) -> Valuation | None   (pure)
  service.py           ValuationService: fetch, store, value, recompute
  sources/
    __init__.py        (empty)
    apify.py           ApifyClient, SourceError
    ebay_sold.py       ApifyEbaySoldSource
    chrono24.py        ApifyChrono24Source
server/watchbox/db.py            (rewritten: new columns and tables, functions)
server/watchbox/refresh.py       (delegate to provider.refresh_watch)
server/watchbox/config.py        (apify_token)
server/watchbox/providers.py     (comps source)
server/watchbox/app.py           (detail fields, optional reference, recompute)
server/watchbox/display.py       (low-confidence "?")
server/watchbox/templates/_form.html, index.html, base.html
server/scripts/check_valuation.py
server/tests/fixtures/ebay_sold_116610ln.json, chrono24_116610ln.json
server/tests/test_val_*.py       (one per valuation module)
```

---

### Task 1: Valuation models

**Files:**
- Create: `server/watchbox/valuation/__init__.py` (empty), `server/watchbox/valuation/models.py`
- Test: `server/tests/test_val_models.py`

- [ ] **Step 1: Write the failing test**

`server/tests/test_val_models.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_models.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.valuation'`

- [ ] **Step 3: Implement**

Create an empty `server/watchbox/valuation/__init__.py`.

`server/watchbox/valuation/models.py`:
```python
"""Shared types and vocabularies for the valuation engine."""
from dataclasses import dataclass, field
from datetime import date

CONDITIONS = ("new", "excellent", "very_good", "good", "fair")
BOX_PAPERS = ("full_set", "box_only", "papers_only", "watch_only")
DIALS = ("black", "blue", "white", "silver", "green", "grey", "champagne", "brown", "red", "other")
BRACELETS = ("oyster", "jubilee", "president", "leather", "rubber", "nato", "other")
METALS = ("steel", "yellow_gold", "white_gold", "rose_gold", "two_tone", "platinum", "titanium", "other")

_LABELS = {
    "new": "New / unworn",
    "full_set": "Full set (box & papers)",
    "two_tone": "Two-tone",
    "nato": "NATO",
}


def label(value: str) -> str:
    return _LABELS.get(value, value.replace("_", " ").capitalize())


@dataclass(frozen=True)
class WatchQuery:
    brand: str
    model: str
    reference: str = ""
    year: int | None = None
    condition: str = "excellent"
    box_papers: str = "full_set"
    dial: str | None = None
    bracelet: str | None = None
    metal: str | None = None


@dataclass(frozen=True)
class Comparable:
    source: str  # "ebay" | "chrono24"
    kind: str  # "sold" | "asking"
    price_usd: float
    date: date | None
    title: str
    url: str = ""
    reference: str | None = None
    year: int | None = None
    condition: str | None = None
    box_papers: str | None = None
    dial: str | None = None
    bracelet: str | None = None
    metal: str | None = None
    best_offer: bool = False  # eBay "best offer accepted": the real sale price is unknown


@dataclass
class Valuation:
    estimate_usd: float
    confidence: str  # "high" | "medium" | "low"
    tier: int
    n_ebay: int
    n_c24: int
    ebay_median: float | None
    ebay_p10: float | None
    ebay_p90: float | None
    ebay_min: float | None
    ebay_max: float | None
    c24_median: float | None
    gap: float
    w_ebay: float
    w_c24: float
    backtest_n: int
    backtest_mdape: float | None
    backtest_within10: float | None
    factors: dict
    failed_sources: tuple[str, ...] = field(default=())
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_models.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/valuation server/tests/test_val_models.py
git commit -m "feat: valuation engine models"
```

---

### Task 2: Listing parsers

**Files:**
- Create: `server/watchbox/valuation/parse.py`
- Test: `server/tests/test_val_parse.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_val_parse.py`. The titles are real eBay and Chrono24 listings captured on 2026-10-02:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_parse.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.valuation.parse'`

- [ ] **Step 3: Implement `server/watchbox/valuation/parse.py`**

```python
"""Reads watch details out of listing titles and Chrono24 spec fields. Pure functions."""
import re
import unicodedata
from datetime import date

from .models import DIALS

JUNK_PHRASES = (
    # accessories, not watches
    "box only", "papers only", "strap only", "bracelet only", "links only", "dial only", "bezel insert",
    "crown only", "case back", "instruction manual", "manual only", "booklet",
    # not working, not genuine, or not as the factory made it
    "for parts", "parts only", "for repair", "needs repair", "repair only", "replica", "homage",
    "custom", "customized", "custom made", "aftermarket", "diamonds added", "aftermarket diamond", "iced", "pvd",
    "dlc",
)
# Aftermarket gem work. Factory gem-set models are told apart by their reference suffix, so these phrases only
# count when the watch being valued is not itself gem-set.
GEM_PHRASES = ("diamond", "diamonds", "sapphires", "gem set")
GEM_SET_RE = re.compile(r"\d(rbr|sabr|saru|rbow|tbr|sats|sa)(?![a-z])")  # tolerates "-0011" bracelet codes
DEALER_WARRANTY_RE = re.compile(
    r"(?<![a-z0-9])(((?!5[\s-]*(?:years?|yrs?))\d+|one|two|three)[\s-]*(years?|yrs?|months?)|lifetime)"
    r"\s+warranty(?![a-z0-9])")  # not 5 years: that is Rolex's own warranty card
FULL_SET_PHRASES = ("b&p", "b & p", "box and papers", "box & papers", "box/papers", "box papers",
                    "full set", "complete set", "box paper", "box & paper", "b+p")
YEAR_RE = re.compile(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)")
DIAL_RE = re.compile(r"(?<![a-z])(black|blue|white|silver|green|grey|gray|champagne|brown|red)\s+dial")
STRAP_RE = re.compile(r"(?<![a-z])(oyster|leather|rubber)\s+(bracelet|strap|band)")


def _fold(text: str | None) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(text))


def _has(text: str, phrase: str) -> bool:
    """Whole-word / whole-phrase match on already-lowercased text."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def is_junk(title: str | None, reference: str | None = None) -> bool:
    t = (title or "").lower()
    if any(_has(t, p) for p in JUNK_PHRASES):
        return True
    if GEM_SET_RE.search(norm(reference)):
        return False
    return any(_has(t, p) for p in GEM_PHRASES)


def reference_matches(reference: str | None, *texts: str | None) -> bool:
    """True if the reference appears in any text, tolerating spaces, dashes, dots and slashes inside it but not
    extra digits around it ("16610LN" must not match "116610LN"). A suffix-less reference (e.g. "116610")
    intentionally matches all suffixed variants."""
    chars = norm(reference)
    if not chars:
        return False
    pattern = r"(?<![0-9])" + r"[\s\-./]*".join(re.escape(ch) for ch in chars)
    if chars[-1].isdigit():
        pattern += r"(?![0-9])"
    regex = re.compile(pattern)
    return any(regex.search(_fold(t)) for t in texts if t)


def year_from_text(text: str | None) -> int | None:
    t = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", t)
    this_year = date.today().year
    for i, token in enumerate(tokens):
        if not YEAR_RE.fullmatch(token) or int(token) > this_year:
            continue
        neighbours = tokens[max(0, i - 1):i] + tokens[i + 1:i + 2]
        if any(n.startswith(("serv", "polish")) or n in ("sc", "rsc") for n in neighbours):
            continue
        if i >= 2 and tokens[i - 2].startswith("serv"):  # "serviced in 2022"
            continue
        return int(token)
    return None


def box_papers_from_title(title: str | None) -> str | None:
    t = (title or "").lower()
    if _has(t, "watch only"):
        return "watch_only"
    if any(_has(t, p) for p in FULL_SET_PHRASES):
        return "full_set"
    box_neg = _has(t, "no box")
    papers_neg = any(_has(t, p) for p in ("no papers", "no paper", "no card", "no warranty"))
    t = DEALER_WARRANTY_RE.sub(" ", t)  # a dealer's "1 year warranty" is not the Rolex warranty card
    box = _has(t, "box") and not box_neg
    papers = ((_has(t, "papers") and not _has(t, "no papers")) or (_has(t, "paper") and not _has(t, "no paper"))
              or (_has(t, "warranty") and not _has(t, "no warranty")))
    tokens = re.findall(r"[a-z0-9]+", t)
    if not papers and not _has(t, "no card"):
        for i, token in enumerate(tokens):
            if token != "card":
                continue
            near = tokens[max(0, i - 3):i] + tokens[i + 1:i + 4]
            prev = tokens[i - 1] if i else ""
            if prev in ("credit", "debit"):
                continue
            if prev in ("warranty", "rolex", "with") or YEAR_RE.fullmatch(prev) or any(n in ("box", "papers", "paper") for n in near):
                papers = True
                break
    if box and papers:
        return "full_set"
    if box:
        return "box_only"
    if papers:
        return "papers_only"
    if box_neg and not papers:
        return "watch_only"
    return None


NEW_PHRASES = ("unworn", "nos", "new old stock", "bnib", "new with tags")
NOT_NEW_NEXT = ("strap", "band", "bracelet", "york", "service")


def condition_from_title(title: str | None) -> str | None:
    t = (title or "").lower()
    if _has(t, "like new") or _has(t, "mint"):
        return "excellent"
    if not _has(t, "not new"):
        if any(_has(t, p) for p in NEW_PHRASES) or re.search(
                rf"(?<![a-z0-9])brand new(?![a-z0-9])(?!\s+({'|'.join(NOT_NEW_NEXT)}))", t):
            return "new"
        tokens = re.findall(r"[a-z0-9]+", t)
        if tokens[:1] == ["new"] and (len(tokens) < 2 or tokens[1] not in NOT_NEW_NEXT):
            return "new"
    if _has(t, "excellent"):
        return "excellent"
    return None


def dial_from_title(title: str | None) -> str | None:
    m = DIAL_RE.search((title or "").lower())
    if not m:
        return None
    return "grey" if m.group(1) == "gray" else m.group(1)


def bracelet_from_title(title: str | None) -> str | None:
    t = (title or "").lower()
    if _has(t, "oysterflex"):
        return "rubber"
    for word in ("jubilee", "president", "nato"):
        if _has(t, word):
            return word
    m = STRAP_RE.search(t)
    return m.group(1) if m else None


def metal_from_title(title: str | None) -> str | None:
    t = (title or "").lower()
    checks = (
        ("two_tone", ("two tone", "two-tone", "rolesor", "bi-color", "bicolor", "steel and gold", "steel/gold",
                      "gold/steel", "steel & gold")),
        ("white_gold", ("white gold",)),
        ("rose_gold", ("rose gold", "everose", "pink gold", "red gold", "sedna")),
        ("yellow_gold", ("yellow gold",)),
        ("platinum", ("platinum",)),
        ("titanium", ("titanium",)),
        ("steel", ("steel", "stainless", "oystersteel", "ss")),
    )
    for metal, phrases in checks:
        if any(_has(t, p) for p in phrases):
            return metal
    return None


def parse_title(title: str | None) -> dict:
    return {
        "year": year_from_text(title),
        "condition": condition_from_title(title),
        "box_papers": box_papers_from_title(title),
        "dial": dial_from_title(title),
        "bracelet": bracelet_from_title(title),
        "metal": metal_from_title(title),
    }


# Chrono24 spec fields --------------------------------------------------------

_C24_CONDITION = (  # order matters: "like new" before "unworn" before "new"; "very good" before "good"
    ("like new", "excellent"), ("unworn", "new"), ("mint", "excellent"), ("new", "new"),
    ("very good", "very_good"), ("good", "good"), ("fair", "fair"), ("poor", "fair"), ("incomplete", "fair"),
)
_C24_SCOPE = {"WithBoxAndPapers": "full_set", "WithBox": "box_only", "WithPapers": "papers_only",
              "WatchOnly": "watch_only"}


def condition_from_c24(text: str | None, condition_new: bool = False) -> str | None:
    if condition_new:
        return "new"
    t = (text or "").lower()
    for key, value in _C24_CONDITION:
        if key in t:
            return value
    return None


def box_papers_from_c24(scope_enum: str | None, scope_text: str | None) -> str | None:
    if scope_enum in _C24_SCOPE:
        return _C24_SCOPE[scope_enum]
    t = (scope_text or "").lower()
    if not t:
        return None
    box = "original box" in t and "no original box" not in t
    papers = "original papers" in t and "no original papers" not in t
    return {(True, True): "full_set", (True, False): "box_only",
            (False, True): "papers_only", (False, False): "watch_only"}[(box, papers)]


def dial_from_c24(text: str | None) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if t == "gray":
        return "grey"
    return t if t in DIALS else "other"


def bracelet_from_c24(material: str | None) -> str | None:
    t = (material or "").lower()
    if "leather" in t:
        return "leather"
    if "rubber" in t or "silicone" in t:
        return "rubber"
    if any(w in t for w in ("textile", "nylon", "fabric")):
        return "nato"
    return None  # steel/gold bracelets don't say which style (Oyster, Jubilee, ...)


def metal_from_c24(text: str | None) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if "/" in t and "gold" in t and "steel" in t:
        return "two_tone"
    if "white gold" in t:
        return "white_gold"
    if "rose gold" in t or "red gold" in t:
        return "rose_gold"
    if "gold" in t:
        return "yellow_gold"
    for metal in ("platinum", "titanium", "steel"):
        if metal in t:
            return metal
    return "other"
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_parse.py -q`
Expected: `102 passed` (counting each parametrized case).

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/valuation/parse.py server/tests/test_val_parse.py
git commit -m "feat: listing detail parsers and junk filter"
```

---

### Task 3: Apify sources

**Files:**
- Create: `server/watchbox/valuation/sources/__init__.py` (empty), `sources/apify.py`, `sources/ebay_sold.py`, `sources/chrono24.py`
- Create fixtures: `server/tests/fixtures/ebay_sold_116610ln.json`, `server/tests/fixtures/chrono24_116610ln.json`
- Test: `server/tests/test_val_sources.py`

- [ ] **Step 1: Copy the real 2026-10-02 Apify output into fixtures**

```bash
SP="/private/tmp/claude-501/-Users-gabrielfarkas-Library-Application-Support-Claude-scratch-workspaces-e93c23b7-aef5-49bd-94a5-1c524f69f97c-cd0e636b-e726-4903-8c21-20475f575db7-scratch-2026-09-25-895a29/508e98e0-b0a8-4e54-a31c-849c65ff58f8/scratchpad/fixtures"
cp "$SP/ebay_sold_116610.json" server/tests/fixtures/ebay_sold_116610ln.json
cp "$SP/c24_details_116610.json" server/tests/fixtures/chrono24_116610ln.json
python3 -c "import json; print(len(json.load(open('server/tests/fixtures/ebay_sold_116610ln.json'))), len(json.load(open('server/tests/fixtures/chrono24_116610ln.json'))))"
```
Expected: `31 12`

- [ ] **Step 2: Write the failing tests**

`server/tests/test_val_sources.py`:
```python
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from watchbox.valuation.models import WatchQuery
from watchbox.valuation.sources.apify import ApifyClient, SourceError
from watchbox.valuation.sources.chrono24 import ApifyChrono24Source, search_url
from watchbox.valuation.sources.ebay_sold import (ApifyEbaySoldSource, comparable_from_row, ebay_query,
                                                  parse_sold_date)

FIXTURES = Path(__file__).parent / "fixtures"
EBAY_ROWS = json.loads((FIXTURES / "ebay_sold_116610ln.json").read_text())
C24_ROWS = json.loads((FIXTURES / "chrono24_116610ln.json").read_text())
SUB = WatchQuery(brand="Rolex", model="Submariner Date", reference="116610LN")


def client(handler):
    return ApifyClient("secret-token", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_posts_with_bearer_token_and_returns_rows():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert "/acts/memo23~ebay-search-scraper-ppe/run-sync-get-dataset-items" in str(request.url)
        return httpx.Response(201, json=[{"a": 1}])

    assert client(handler).run("memo23/ebay-search-scraper-ppe", {}) == [{"a": 1}]


def test_client_errors_never_include_the_token():
    def handler(request):
        return httpx.Response(400, json={"error": {"type": "run-failed", "message": "Actor run did not succeed"}})

    with pytest.raises(SourceError) as exc:
        client(handler).run("memo23/x", {})
    assert "400" in str(exc.value) and "did not succeed" in str(exc.value)
    assert "secret-token" not in str(exc.value)


def test_client_rejects_non_list_and_transport_errors():
    with pytest.raises(SourceError):
        client(lambda r: httpx.Response(200, json={"not": "a list"})).run("memo23/x", {})

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(SourceError, match="request failed"):
        client(boom).run("memo23/x", {})


def test_ebay_query_and_payload():
    assert ebay_query(SUB) == "Rolex 116610LN"
    assert ebay_query(WatchQuery(brand="Rolex", model="Datejust 41", dial="blue")) == "Rolex Datejust 41 blue"
    payload = ApifyEbaySoldSource(None).payload(SUB)
    assert payload["mode"] == "sold" and payload["soldWithinDays"] == 90 and payload["category"] == "31387"
    assert payload["searchQuery"] == "Rolex 116610LN"


def test_parse_sold_date():
    assert parse_sold_date("Sold  Oct 1, 2026") == date(2026, 10, 1)
    assert parse_sold_date(None) is None
    assert parse_sold_date("Sold  Sep 30, 2026") == date(2026, 9, 30)
    assert parse_sold_date("Sold  Feb 30, 2026") is None


@pytest.mark.parametrize("title, cond, expected", [
    ("Rolex 116610LN", "Brand New", "new"),
    ("Rolex 116610LN", "New with tags", "new"),
    ("Rolex 116610LN", "New without tags", "new"),
    ("New Rolex 116610LN", "Pre-Owned", None),
    ("Rolex 116610LN brand new", "Pre-Owned", None),
    ("Rolex 116610LN mint", "Pre-Owned", "excellent"),
    ("Rolex 116610LN", "Pre-Owned", None),
])
def test_ebay_row_condition_overrides_title(title, cond, expected):
    row = {"title": title, "priceValue": 10000, "currency": "USD", "condition": cond}
    assert comparable_from_row(row).condition == expected


def test_client_redacts_token_from_errors():
    def handler(request):
        return httpx.Response(500, text="oops secret-token leaked")

    with pytest.raises(SourceError) as exc:
        client(handler).run("memo23/x", {})
    assert "secret-token" not in str(exc.value) and "***" in str(exc.value)


def test_ebay_source_parses_fixture():
    comps = ApifyEbaySoldSource(client(lambda r: httpx.Response(201, json=EBAY_ROWS))).fetch(SUB)
    assert len(comps) == 30  # the summary row is skipped
    assert sum(c.best_offer for c in comps) == 4
    assert all(c.source == "ebay" and c.kind == "sold" and c.price_usd > 0 for c in comps)
    assert any(c.box_papers == "full_set" for c in comps)


def test_chrono24_search_url():
    url = search_url(SUB)
    assert "query=Rolex+116610LN" in url and "currencyId=USD" in url


def test_chrono24_source_parses_fixture_details():
    comps = ApifyChrono24Source(client(lambda r: httpx.Response(201, json=C24_ROWS))).fetch(SUB)
    assert len(comps) == 12
    first = comps[0]
    assert (first.price_usd, first.condition, first.box_papers, first.year, first.dial, first.metal) == (
        11200.0, "good", "watch_only", 2015, "black", "steel")
    assert first.reference == "126610LN" and "116610LN" in first.title  # mislabelled reference, real one in the title
    assert comps[1].box_papers == "full_set" and comps[1].condition == "very_good"
    assert comps[5].year == 2014  # "2014 (Approximation)"
    assert comps[10].condition == "excellent"  # "Like new & unworn" (not flagged conditionNew)
```

- [ ] **Step 3: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_sources.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.valuation.sources'`

- [ ] **Step 4: Implement**

Create an empty `server/watchbox/valuation/sources/__init__.py`.

`server/watchbox/valuation/sources/apify.py`:
```python
"""Minimal client for running Apify actors synchronously and reading their dataset."""
import httpx

API = "https://api.apify.com/v2"


class SourceError(Exception):
    pass


class ApifyClient:
    def _redact(self, message: str) -> str:
        return message.replace(self._token, "***") if self._token else message

    def __init__(self, token: str, http: httpx.Client | None = None, timeout_s: int = 300):
        self._token = token
        self._http = http or httpx.Client()
        self._timeout_s = timeout_s

    def run(self, actor: str, payload: dict) -> list[dict]:
        url = f"{API}/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items"
        try:
            response = self._http.post(url, params={"timeout": self._timeout_s}, json=payload,
                                       headers={"Authorization": f"Bearer {self._token}"},
                                       timeout=self._timeout_s + 30)
        except httpx.HTTPError as e:
            raise SourceError(self._redact(f"{actor}: request failed ({type(e).__name__})")) from None
        if response.status_code not in (200, 201):
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text[:200]
            raise SourceError(self._redact(f"{actor}: HTTP {response.status_code} {message}"))
        try:
            data = response.json()
        except ValueError:
            raise SourceError(f"{actor}: response was not JSON") from None
        if not isinstance(data, list):
            raise SourceError(f"{actor}: unexpected response shape")
        return data
```

`server/watchbox/valuation/sources/ebay_sold.py`:
```python
"""eBay sold listings (last 90 days) via the memo23 eBay scraper on Apify."""
import re
from datetime import date

from ..models import Comparable, WatchQuery
from ..parse import parse_title
from .apify import ApifyClient

ACTOR = "memo23/ebay-search-scraper-ppe"
WRISTWATCHES = "31387"
MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}
NEW_CONDITIONS = ("brand new", "new with tags", "new without tags")
SOLD_DATE_RE = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")


def ebay_query(q: WatchQuery) -> str:
    if q.reference:
        return f"{q.brand} {q.reference}"
    parts = [q.brand, q.model]
    if q.dial and q.dial != "other":
        parts.append(q.dial)
    return " ".join(parts)


def parse_sold_date(text: str | None) -> date | None:
    m = SOLD_DATE_RE.search(text or "")
    if not m or m.group(1) not in MONTHS:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    except ValueError:
        return None


def comparable_from_row(row: dict) -> Comparable | None:
    if row.get("type") == "sold-price-summary":
        return None
    price = row.get("priceValue")
    if not isinstance(price, (int, float)) or price <= 0 or (row.get("currency") or "USD") != "USD":
        return None
    title = row.get("title") or ""
    details = parse_title(title)
    listed = (row.get("condition") or "").strip().lower()
    if listed in NEW_CONDITIONS:
        details["condition"] = "new"
    elif listed and details["condition"] == "new":
        details["condition"] = None  # eBay lists it as used, so a "new" in the title is not about the watch
    return Comparable(source="ebay", kind="sold", price_usd=float(price), date=parse_sold_date(row.get("soldDate")),
                      title=title, url=row.get("url") or "", best_offer=bool(row.get("bestOfferAccepted")),
                      **details)


class ApifyEbaySoldSource:
    name = "ebay"

    def __init__(self, client: ApifyClient):
        self._client = client

    def payload(self, q: WatchQuery) -> dict:
        return {"searchQuery": ebay_query(q), "marketplace": "ebay.com", "mode": "sold", "soldWithinDays": 90,
                "category": WRISTWATCHES, "maxItems": 60, "includeSummary": False, "detailedItems": False}

    def fetch(self, q: WatchQuery) -> list[Comparable]:
        rows = self._client.run(ACTOR, self.payload(q))
        return [c for c in map(comparable_from_row, rows) if c is not None]
```

`server/watchbox/valuation/sources/chrono24.py`:
```python
"""Chrono24 asking prices, with full listing details, via the memo23 Chrono24 scraper on Apify."""
from datetime import date
from urllib.parse import urlencode

from ..models import Comparable, WatchQuery
from ..parse import (box_papers_from_c24, bracelet_from_c24, condition_from_c24, dial_from_c24, metal_from_c24,
                     parse_title, year_from_text)
from .apify import ApifyClient

ACTOR = "memo23/chrono24-scraper"


def search_url(q: WatchQuery) -> str:
    query = f"{q.brand} {q.reference}" if q.reference else f"{q.brand} {q.model}"
    return "https://www.chrono24.com/search/index.htm?" + urlencode(
        {"query": query, "dosearch": "true", "currencyId": "USD"})


def comparable_from_row(row: dict) -> Comparable | None:
    price = row.get("price")
    if not isinstance(price, (int, float)) or price <= 0 or row.get("currency") != "USD":
        return None
    title = " ".join(p for p in (row.get("title"), row.get("subtitle")) if p)
    guessed = parse_title(title)
    scraped = row.get("scrapedAt")
    return Comparable(
        source="chrono24", kind="asking", price_usd=float(price),
        date=date.fromisoformat(scraped[:10]) if scraped else None,
        title=title, url=row.get("listingUrl") or "",
        reference=row.get("specs_referencenumber") or row.get("referenceNumber"),
        year=year_from_text(row.get("specs_year")) or guessed["year"],
        condition=condition_from_c24(row.get("specs_condition"), row.get("conditionNew") is True) or guessed["condition"],
        box_papers=box_papers_from_c24(row.get("scopeOfDelivery"), row.get("specs_scopeofdelivery"))
        or guessed["box_papers"],
        dial=dial_from_c24(row.get("specs_dialcolor")) or guessed["dial"],
        bracelet=bracelet_from_c24(row.get("specs_braceletmaterial")) or guessed["bracelet"],
        metal=metal_from_c24(row.get("specs_casematerial")) or guessed["metal"],
    )


class ApifyChrono24Source:
    name = "chrono24"

    def __init__(self, client: ApifyClient):
        self._client = client

    def payload(self, q: WatchQuery) -> dict:
        return {"startUrls": [search_url(q)], "fetchListingDetails": True, "maxIndexPages": 1, "maxItems": 40}

    def fetch(self, q: WatchQuery) -> list[Comparable]:
        rows = self._client.run(ACTOR, self.payload(q))
        return [c for c in map(comparable_from_row, rows) if c is not None]
```

- [ ] **Step 5: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_sources.py -q`
Expected: `16 passed`

- [ ] **Step 6: Commit**

```bash
git add server/watchbox/valuation/sources server/tests/test_val_sources.py server/tests/fixtures/ebay_sold_116610ln.json server/tests/fixtures/chrono24_116610ln.json
git commit -m "feat: Apify eBay sold and Chrono24 comparable sources"
```

---

### Task 4: Matching tiers and trimming

**Files:**
- Create: `server/watchbox/valuation/match.py`
- Test: `server/tests/test_val_match.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_val_match.py`:
```python
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


def test_iqr_mask_matches_trim_iqr():
    from watchbox.valuation.match import iqr_mask
    assert iqr_mask([10, 11, 12, 13, 100]) == [True, True, True, True, False]
    assert iqr_mask([10, 100, 1000]) == [True, True, True]


def test_tier_3_is_superset_of_tier_2():
    assert in_tier(comp("Rolex Submariner 116610LN"), Q, 3)  # no "Date", but the reference matches
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_match.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement `server/watchbox/valuation/match.py`**

```python
"""Chooses which comparables describe the owner's watch closely enough, and trims outliers."""
from statistics import median, quantiles

from .models import Comparable, WatchQuery
from .parse import norm, reference_matches

MIN_TIER_COUNT = 5
YEAR_WINDOW = 3
MIN_SPREAD = 0.06  # IQR floor, as a share of the median
DETAIL_FIELDS = ("dial", "bracelet", "metal")


def _brand_model_match(c: Comparable, q: WatchQuery) -> bool:
    text = norm(f"{c.title} {c.reference or ''}")
    words = [norm(w) for w in q.model.split() if norm(w)]
    return norm(q.brand) in text and all(w in text for w in words)


def _base_match(c: Comparable, q: WatchQuery) -> bool:
    return reference_matches(q.reference, c.title, c.reference) if q.reference else _brand_model_match(c, q)


def _details_match(c: Comparable, q: WatchQuery) -> bool:
    """Every detail the owner set must match; a listing that doesn't mention it is neutral."""
    return all(getattr(c, f) is None or getattr(c, f) == getattr(q, f) for f in DETAIL_FIELDS if getattr(q, f))


def in_tier(c: Comparable, q: WatchQuery, tier: int) -> bool:
    if tier == 1:
        return _base_match(c, q) and _details_match(c, q)
    if tier == 2:
        return _base_match(c, q)
    return _base_match(c, q) or _brand_model_match(c, q)


def prefer_year(comps: list[Comparable], q: WatchQuery) -> list[Comparable]:
    """With a year set, drop listings more than 3 years away (unknown years stay) if enough remain."""
    if q.year is None:
        return comps
    close = [c for c in comps if c.year is None or abs(c.year - q.year) <= YEAR_WINDOW]
    return close if len(close) >= MIN_TIER_COUNT else comps


def select_tier(comps: list[Comparable], q: WatchQuery) -> tuple[int, list[Comparable]]:
    best: tuple[int, list[Comparable]] = (3, [])
    for tier in (1, 2, 3):
        chosen = prefer_year([c for c in comps if in_tier(c, q, tier)], q)
        if len(chosen) >= MIN_TIER_COUNT:
            return tier, chosen
        if len(chosen) > len(best[1]):
            best = (tier, chosen)
    return best


def iqr_mask(values: list[float]) -> list[bool]:
    """True for each value inside [Q1 - 1.5 IQR, Q3 + 1.5 IQR]; with fewer than 4 values all are kept."""
    if len(values) < 4:
        return [True] * len(values)
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    spread = max(q3 - q1, MIN_SPREAD * median(values))  # tied prices must not collapse the sample
    low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
    return [low <= v <= high for v in values]


def trim_iqr(values: list[float]) -> list[float]:
    return [v for v, keep in zip(values, iqr_mask(values)) if keep]
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_match.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/valuation/match.py server/tests/test_val_match.py
git commit -m "feat: comparable matching tiers and IQR trimming"
```

---

### Task 5: Adjustments

**Files:**
- Create: `server/watchbox/valuation/adjust.py`
- Test: `server/tests/test_val_adjust.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_val_adjust.py`:
```python
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


def test_learned_factor_never_beats_the_better_level():
    comps = [comp(10000.0, "full_set")] * 5 + [comp(12000.0, "papers_only")] * 5
    assert learn_factors(comps).box["papers_only"] == 1.0  # shrunk 1.04 is capped at the baseline


def test_learned_factor_is_clamped_and_needs_enough_data():
    comps = [comp(10000.0, "full_set")] * 5 + [comp(5000.0, "watch_only")] * 5
    assert learn_factors(comps).box["watch_only"] == pytest.approx(0.75)  # prior 0.85 - 0.10
    few = [comp(10000.0, "full_set")] * 5 + [comp(8000.0, "watch_only")] * 2
    assert learn_factors(few).box["watch_only"] == BOX_PRIOR["watch_only"]
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_adjust.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement `server/watchbox/valuation/adjust.py`**

```python
"""Box & papers and condition adjustments: priors, nudged by what the watch's own listings show."""
from dataclasses import dataclass
from statistics import median
from typing import Callable

from .models import Comparable, WatchQuery

BOX_PRIOR = {"full_set": 1.00, "papers_only": 0.94, "box_only": 0.92, "watch_only": 0.85}
COND_PRIOR = {"new": 1.10, "excellent": 1.00, "very_good": 0.96, "good": 0.90, "fair": 0.80}
SHRINK = 10  # how many comparables a measured factor needs before it outweighs the prior
CLAMP = 0.10  # a learned factor stays within ±0.10 of its prior
MIN_GROUP = 3


@dataclass
class Factors:
    box: dict[str, float]
    condition: dict[str, float]
    learned: dict[str, float]  # raw measured ratios, for inspection

    def factor(self, box_papers: str | None, condition: str | None) -> float:
        box = self.box.get(box_papers, 1.0) if box_papers else 1.0
        cond = self.condition.get(condition, 1.0) if condition else 1.0
        return box * cond

    def to_baseline(self, c: Comparable) -> float:
        """The comparable's price as if it were a full set in excellent condition."""
        return c.price_usd / self.factor(c.box_papers, c.condition)


def adjust_price(c: Comparable, factors: Factors, q: WatchQuery) -> float:
    return factors.to_baseline(c) * factors.factor(q.box_papers, q.condition)


def _measured(comps, attr, value, baseline, other_factor: Callable[[Comparable], float]):
    """Median price ratio of `value` vs `baseline` within each source, pooled by count. None if too little data."""
    ratios = []
    for source in sorted({c.source for c in comps}):
        group = [c.price_usd / other_factor(c) for c in comps if c.source == source and getattr(c, attr) == value]
        base = [c.price_usd / other_factor(c) for c in comps if c.source == source and getattr(c, attr) == baseline]
        if len(group) >= MIN_GROUP and len(base) >= MIN_GROUP:
            ratios.append((median(group) / median(base), len(group)))
    if not ratios:
        return None
    n = sum(k for _, k in ratios)
    return sum(r * k for r, k in ratios) / n, n


def _shrink(measured: float, n: int, prior: float, lo: float | None = None, hi: float | None = None) -> float:
    """Shrink toward the prior, stay within ±CLAMP of it and within the optional [lo, hi] bounds."""
    blended = (n * measured + SHRINK * prior) / (n + SHRINK)
    value = min(max(blended, prior - CLAMP), prior + CLAMP)
    if lo is not None:
        value = max(value, lo)
    if hi is not None:
        value = min(value, hi)
    return value


def learn_factors(comps: list[Comparable]) -> Factors:
    box, cond, learned = dict(BOX_PRIOR), dict(COND_PRIOR), {}
    cond_prior = lambda c: COND_PRIOR.get(c.condition, 1.0) if c.condition else 1.0
    for value in BOX_PRIOR:
        if value == "full_set":
            continue
        m = _measured(comps, "box_papers", value, "full_set", cond_prior)
        if m:
            box[value] = _shrink(m[0], m[1], BOX_PRIOR[value], hi=1.0)  # never beats a full set
            learned[f"box:{value}"] = m[0]
    box_learned = lambda c: box.get(c.box_papers, 1.0) if c.box_papers else 1.0
    for value in COND_PRIOR:
        if value == "excellent":
            continue
        m = _measured(comps, "condition", value, "excellent", box_learned)
        if m:
            # "new" never ranks below excellent; every lower grade never ranks above it
            cond[value] = _shrink(m[0], m[1], COND_PRIOR[value], lo=1.0 if value == "new" else None,
                                  hi=None if value == "new" else 1.0)
            learned[f"condition:{value}"] = m[0]
    return Factors(box, cond, learned)
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_adjust.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/valuation/adjust.py server/tests/test_val_adjust.py
git commit -m "feat: box & papers and condition adjustments"
```

---

### Task 6: Blend, confidence and backtest

**Files:**
- Create: `server/watchbox/valuation/blend.py`, `server/watchbox/valuation/backtest.py`
- Test: `server/tests/test_val_blend.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_val_blend.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_blend.py -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3: Implement `server/watchbox/valuation/blend.py`**

```python
"""Combining sources into one estimate, and how sure we are about it."""
import math
from statistics import median

W_EBAY, W_C24 = 0.7, 0.3
FULL_WEIGHT_N = 10  # a source gets its full weight from 10 comparables
DEFAULT_GAP, MAX_GAP = 0.07, 0.20
MIN_GAP_SAMPLES = 5
GAP_SHRINK = 10
LEVELS = ("low", "medium", "high")


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def asking_gap(ebay_baseline: list[float], c24_baseline: list[float]) -> float:
    """How far Chrono24 asking prices sit above eBay sold prices for this watch (0-20%)."""
    if len(ebay_baseline) < MIN_GAP_SAMPLES or len(c24_baseline) < MIN_GAP_SAMPLES:
        return DEFAULT_GAP
    measured = 1 - median(ebay_baseline) / median(c24_baseline)
    n = min(len(ebay_baseline), len(c24_baseline))
    gap = (n * measured + GAP_SHRINK * DEFAULT_GAP) / (n + GAP_SHRINK)  # few samples: stay near the default
    return min(max(gap, 0.0), MAX_GAP)


def weights(n_ebay: int, n_c24: int) -> tuple[float, float]:
    w_ebay = W_EBAY * min(1.0, n_ebay / FULL_WEIGHT_N)
    w_c24 = W_C24 * min(1.0, n_c24 / FULL_WEIGHT_N)
    total = w_ebay + w_c24
    return (w_ebay / total, w_c24 / total) if total else (0.0, 0.0)


def confidence(tier: int, n_total: int, spread: float, mdape: float | None,
               estimated_reference: bool, degraded: bool,
               sold_data: bool = True, loose_match: bool = False) -> str:
    if tier <= 2 and n_total >= 10 and spread <= 0.25 and (mdape is None or mdape <= 0.07):
        level = 2
    elif n_total >= 5 and spread <= 0.45:
        level = 1
    else:
        level = 0
    if estimated_reference or not sold_data:  # no eBay sold prices: asking prices only
        level = min(level, 1)
    if loose_match:  # tier 3 although the owner set a reference
        level = 0
    if degraded:  # a source failed this time
        level = max(level - 1, 0)
    return LEVELS[level]
```

- [ ] **Step 4: Implement `server/watchbox/valuation/backtest.py`**

```python
"""Leave-one-out accuracy check: predict each recent sale from the others and measure the error."""
from statistics import median

from .adjust import Factors
from .match import trim_iqr
from .models import Comparable

MIN_BACKTEST = 6


def backtest(sold: list[Comparable], factors: Factors) -> tuple[int, float | None, float | None]:
    """Returns (sales tested, median absolute % error, share within ±10%)."""
    if len(sold) < MIN_BACKTEST:
        return 0, None, None
    errors = []
    for i, target in enumerate(sold):
        others = sold[:i] + sold[i + 1:]
        target_factor = factors.factor(target.box_papers, target.condition)
        predicted = median(trim_iqr([factors.to_baseline(o) * target_factor for o in others]))
        errors.append(abs(predicted - target.price_usd) / target.price_usd)
    return len(errors), median(errors), sum(e <= 0.10 for e in errors) / len(errors)
```

- [ ] **Step 5: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_blend.py -q`
Expected: `14 passed`

- [ ] **Step 6: Commit**

```bash
git add server/watchbox/valuation/blend.py server/watchbox/valuation/backtest.py server/tests/test_val_blend.py
git commit -m "feat: source blending, confidence and leave-one-out backtest"
```

---

### Task 7: Engine

**Files:**
- Create: `server/watchbox/valuation/engine.py`
- Test: `server/tests/test_val_engine.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_val_engine.py`:
```python
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
    comps = [comp(10000.0 + i, title="Rolex Submariner Date 126610LN") for i in range(12)]
    v = value(SUB, comps)
    assert v is None or v.tier != 3 or v.confidence == "low"


def test_fewer_than_three_comparables_returns_none():
    assert value(SUB, [comp(10000.0), comp(10100.0)]) is None


def test_estimate_rounds_half_up():
    v = value(SUB, [comp(10005.0) for _ in range(6)])
    assert v.estimate_usd == 10010.0
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_engine.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.valuation.engine'`

- [ ] **Step 3: Implement `server/watchbox/valuation/engine.py`**

```python
"""Turns comparables into one valuation for a watch. Pure: no network, no database."""
from statistics import median

from .adjust import adjust_price, learn_factors
from .backtest import backtest
from .blend import asking_gap, confidence, percentile, weights
from .match import iqr_mask, select_tier
from .models import Comparable, Valuation, WatchQuery
from .parse import is_junk

MIN_COMPARABLES = 3


def _kept(comps: list[Comparable], adjusted: list[float]) -> tuple[list[Comparable], list[float]]:
    """Comparables whose adjusted price survives outlier trimming, with those adjusted prices."""
    mask = iqr_mask(adjusted)
    return [c for c, k in zip(comps, mask) if k], [a for a, k in zip(adjusted, mask) if k]


def value(query: WatchQuery, comps: list[Comparable], estimated_reference: bool = False,
          failed_sources: tuple[str, ...] = ()) -> Valuation | None:
    # best-offer sales hide the real price: leave them out before tiers and factors see them
    usable = [c for c in comps if c.price_usd > 0 and not c.best_offer and not is_junk(c.title, query.reference)]
    tier, chosen = select_tier(usable, query)
    if not chosen:
        return None
    factors = learn_factors(chosen)
    ebay_all = [c for c in chosen if c.source == "ebay" and c.kind == "sold"]
    c24_all = [c for c in chosen if c.source == "chrono24"]

    ebay, ebay_adj = _kept(ebay_all, [adjust_price(c, factors, query) for c in ebay_all])
    c24, c24_adj = _kept(c24_all, [adjust_price(c, factors, query) for c in c24_all])
    gap = asking_gap([factors.to_baseline(c) for c in ebay], [factors.to_baseline(c) for c in c24])
    w_ebay, w_c24 = weights(len(ebay_adj), len(c24_adj))
    if w_ebay + w_c24 == 0:
        return None
    ebay_est = median(ebay_adj) if ebay_adj else 0.0
    c24_est = median(c24_adj) * (1 - gap) if c24_adj else 0.0
    estimate = int((w_ebay * ebay_est + w_c24 * c24_est) / 10 + 0.5) * 10

    combined = ebay_adj + [p * (1 - gap) for p in c24_adj]
    if len(combined) < MIN_COMPARABLES:
        return None
    mid = median(combined)
    spread = (percentile(combined, 90) - percentile(combined, 10)) / mid if mid else 1.0
    bt_n, bt_mdape, bt_within = backtest(ebay, factors)

    ebay_raw = [c.price_usd for c in ebay]  # shown to the owner as-is, before adjustments
    c24_raw = [c.price_usd for c in c24]
    return Valuation(
        estimate_usd=float(estimate),
        confidence=confidence(tier, len(combined), spread, bt_mdape, estimated_reference, bool(failed_sources),
                              sold_data=bool(ebay), loose_match=tier == 3 and bool(query.reference)),
        tier=tier, n_ebay=len(ebay), n_c24=len(c24),
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
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_val_engine.py -q`
Expected: all pass. If `test_real_submariner_data_gives_a_sensible_estimate` fails, print `value(SUB, real_comps)` and report the numbers. Don't loosen the assertion without the coordinator's approval: a failure here is real information about the engine.

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/valuation/engine.py server/tests/test_val_engine.py
git commit -m "feat: valuation engine combining sources, adjustments and backtest"
```

---

### Task 8: Storage

**Files:**
- Modify (full rewrite shown): `server/watchbox/db.py`
- Test: `server/tests/test_db_valuation.py` (new; the existing `test_db.py` must still pass)

- [ ] **Step 1: Write the failing tests**

`server/tests/test_db_valuation.py`:
```python
import sqlite3
from datetime import date

import pytest

from watchbox import db
from watchbox.pricing import PriceResult
from watchbox.valuation.models import Comparable, Valuation


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def val(estimate=11500.0, **kw):
    base = dict(estimate_usd=estimate, confidence="high", tier=1, n_ebay=20, n_c24=8, ebay_median=11500.0,
                ebay_p10=10500.0, ebay_p90=12900.0, ebay_min=9800.0, ebay_max=13300.0, c24_median=12400.0,
                gap=0.07, w_ebay=0.7, w_c24=0.3, backtest_n=20, backtest_mdape=0.04, backtest_within10=0.9,
                factors={"box": {"full_set": 1.0}})
    return Valuation(**(base | kw))


def comp(source="ebay", price=11000.0):
    return Comparable(source=source, kind="sold" if source == "ebay" else "asking", price_usd=price,
                      date=date(2026, 9, 30), title="Rolex 116610LN", box_papers="full_set", best_offer=False)


def test_details_are_stored_and_build_the_query(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 4, None, year=2015, condition="good",
                       box_papers="watch_only", dial="black", bracelet="oyster", metal="steel")
    w = db.get_watch(conn, wid)
    assert (w.year, w.condition, w.box_papers, w.dial, w.bracelet, w.metal) == (
        2015, "good", "watch_only", "black", "oyster", "steel")
    assert w.query.reference == "116610LN" and w.query.condition == "good"


def test_defaults_and_optional_reference(conn):
    w = db.get_watch(conn, db.add_watch(conn, "Glashütte Original", "Sixties Panorama Date", "", None, None))
    assert (w.reference, w.condition, w.box_papers, w.year) == ("", "excellent", "full_set", None)


def test_comparables_are_replaced_per_source_and_round_trip(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "ebay", [comp("ebay")] * 3)
    db.replace_comparables(conn, wid, "chrono24", [comp("chrono24")] * 2)
    db.replace_comparables(conn, wid, "ebay", [comp("ebay", 12000.0)])
    loaded = db.load_comparables(conn, wid)
    assert sorted((c.source, c.price_usd) for c in loaded) == [("chrono24", 11000.0), ("chrono24", 11000.0),
                                                               ("ebay", 12000.0)]
    assert loaded[0].date == date(2026, 9, 30) and loaded[0].box_papers == "full_set"


def test_latest_valuation_becomes_the_price(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)
    db.add_price(conn, wid, PriceResult(12413.0, 270, "thewatchapi", as_of="2024-07-17"),
                 fetched_at="2026-09-01T00:00:00+00:00")
    db.add_valuation(conn, wid, val(11000.0), as_of="2026-10-01T00:00:00+00:00")
    db.add_valuation(conn, wid, val(11500.0, confidence="low", failed_sources=("chrono24",)),
                     as_of="2026-10-02T00:00:00+00:00")
    w = db.get_watch(conn, wid)
    assert (w.price_usd, w.price_source, w.price_date, w.confidence, w.sample_size) == (
        11500.0, "comps", None, "low", 28)
    latest = db.latest_valuation(conn, wid)
    assert latest["failed_sources"] == ("chrono24",) and latest["factors"] == {"box": {"full_set": 1.0}}
    assert db.latest_valuations(conn)[wid]["estimate_usd"] == 11500.0
    assert db.latest_fetch_time(conn) == "2026-10-02T00:00:00+00:00"


def test_identity_change_clears_market_data_but_detail_change_keeps_it(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "ebay", [comp()])
    db.add_valuation(conn, wid, val())
    db.update_watch(conn, wid, "Rolex", "Submariner", "116610LN", 1, None, condition="good")
    assert db.load_comparables(conn, wid) and db.latest_valuation(conn, wid)
    db.update_watch(conn, wid, "Rolex", "Submariner", "126610LN", 1, None)
    assert db.load_comparables(conn, wid) == [] and db.latest_valuation(conn, wid) is None


def test_model_change_without_reference_clears_market_data(conn):
    wid = db.add_watch(conn, "Glashütte Original", "Sixties", "", 3, None)
    db.add_valuation(conn, wid, val())
    db.update_watch(conn, wid, "Glashütte Original", "Sixties Panorama Date", "", 3, None)
    assert db.latest_valuation(conn, wid) is None


def test_old_databases_are_migrated(tmp_path):
    path = tmp_path / "v0.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE watches (id INTEGER PRIMARY KEY AUTOINCREMENT, brand TEXT NOT NULL, model TEXT NOT NULL,
            reference TEXT NOT NULL, slot INTEGER UNIQUE CHECK (slot BETWEEN 1 AND 8), nickname TEXT,
            created_at TEXT NOT NULL);
        CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER NOT NULL REFERENCES watches(id)
            ON DELETE CASCADE, price_usd REAL NOT NULL, sample_size INTEGER NOT NULL, source TEXT NOT NULL,
            fetched_at TEXT NOT NULL);
        INSERT INTO watches (brand, model, reference, slot, nickname, created_at)
            VALUES ('Rolex', 'Submariner', '116610LN', 4, NULL, '2026-09-29T00:00:00+00:00');
    """)
    old.commit()
    old.close()
    conn = db.connect(path)
    try:
        w = db.list_watches(conn)[0]
        assert (w.condition, w.box_papers, w.year, w.price_reference) == ("excellent", "full_set", None, None)
        db.add_valuation(conn, w.id, val())
        assert db.get_watch(conn, w.id).price_usd == 11500.0
    finally:
        conn.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_db_valuation.py -q`
Expected: FAIL (`TypeError: add_watch() got an unexpected keyword argument 'year'` or `AttributeError`).

- [ ] **Step 3: Replace `server/watchbox/db.py` with:**

```python
"""SQLite storage for watches, their prices, comparables and valuations."""
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from os import PathLike

from .pricing import PriceResult
from .valuation.models import Comparable, Valuation, WatchQuery

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    reference TEXT NOT NULL,
    slot INTEGER UNIQUE CHECK (slot BETWEEN 1 AND 8),
    nickname TEXT,
    created_at TEXT NOT NULL,
    price_reference TEXT,
    year INTEGER,
    condition TEXT NOT NULL DEFAULT 'excellent',
    box_papers TEXT NOT NULL DEFAULT 'full_set',
    dial TEXT,
    bracelet TEXT,
    metal TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    price_usd REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    price_date TEXT
);
CREATE TABLE IF NOT EXISTS comparables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    price_usd REAL NOT NULL,
    date TEXT,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    reference TEXT,
    year INTEGER,
    condition TEXT,
    box_papers TEXT,
    dial TEXT,
    bracelet TEXT,
    metal TEXT,
    best_offer INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valuations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    estimate_usd REAL NOT NULL,
    confidence TEXT NOT NULL,
    tier INTEGER NOT NULL,
    n_ebay INTEGER NOT NULL,
    n_c24 INTEGER NOT NULL,
    ebay_median REAL, ebay_p10 REAL, ebay_p90 REAL, ebay_min REAL, ebay_max REAL,
    c24_median REAL,
    gap REAL NOT NULL,
    w_ebay REAL NOT NULL,
    w_c24 REAL NOT NULL,
    backtest_n INTEGER NOT NULL,
    backtest_mdape REAL,
    backtest_within10 REAL,
    factors_json TEXT NOT NULL,
    failed_sources TEXT NOT NULL DEFAULT '',
    as_of TEXT NOT NULL
);
"""

# Columns added after a table was first released: (table, column, declaration).
MIGRATIONS = (
    ("prices", "price_date", "TEXT"),
    ("watches", "price_reference", "TEXT"),
    ("watches", "year", "INTEGER"),
    ("watches", "condition", "TEXT NOT NULL DEFAULT 'excellent'"),
    ("watches", "box_papers", "TEXT NOT NULL DEFAULT 'full_set'"),
    ("watches", "dial", "TEXT"),
    ("watches", "bracelet", "TEXT"),
    ("watches", "metal", "TEXT"),
)

_SELECT = """
SELECT w.id, w.brand, w.model, w.reference, w.slot, w.nickname, w.price_reference,
       w.year, w.condition, w.box_papers, w.dial, w.bracelet, w.metal,
       COALESCE(v.estimate_usd, p.price_usd) AS price_usd,
       CASE WHEN v.id IS NOT NULL THEN v.n_ebay + v.n_c24 ELSE p.sample_size END AS sample_size,
       COALESCE(v.as_of, p.fetched_at) AS fetched_at,
       CASE WHEN v.id IS NOT NULL THEN 'comps' ELSE p.source END AS price_source,
       CASE WHEN v.id IS NOT NULL THEN NULL ELSE p.price_date END AS price_date,
       v.confidence AS confidence
FROM watches w
LEFT JOIN prices p ON p.id = (
    SELECT id FROM prices WHERE watch_id = w.id ORDER BY fetched_at DESC, id DESC LIMIT 1
)
LEFT JOIN valuations v ON v.id = (
    SELECT id FROM valuations WHERE watch_id = w.id ORDER BY as_of DESC, id DESC LIMIT 1
)
"""

DETAIL_DEFAULTS = {"year": None, "condition": "excellent", "box_papers": "full_set",
                   "dial": None, "bracelet": None, "metal": None}
VALUATION_COLUMNS = ("estimate_usd", "confidence", "tier", "n_ebay", "n_c24", "ebay_median", "ebay_p10",
                     "ebay_p90", "ebay_min", "ebay_max", "c24_median", "gap", "w_ebay", "w_c24", "backtest_n",
                     "backtest_mdape", "backtest_within10")
COMPARABLE_COLUMNS = ("source", "kind", "price_usd", "date", "title", "url", "reference", "year", "condition",
                      "box_papers", "dial", "bracelet", "metal", "best_offer")


@dataclass
class Watch:
    id: int
    brand: str
    model: str
    reference: str
    slot: int | None
    nickname: str | None
    price_reference: str | None = None  # look prices up under this reference instead (an estimate)
    year: int | None = None
    condition: str = "excellent"
    box_papers: str = "full_set"
    dial: str | None = None
    bracelet: str | None = None
    metal: str | None = None
    price_usd: float | None = None
    sample_size: int | None = None
    fetched_at: str | None = None
    price_source: str | None = None
    price_date: str | None = None
    confidence: str | None = None

    @property
    def pricing_reference(self) -> str:
        return self.price_reference or self.reference

    @property
    def identity(self) -> tuple:
        """What the market data depends on; when it changes, prices must be fetched again."""
        return (self.brand, self.model, self.reference, self.price_reference)

    @property
    def query(self) -> WatchQuery:
        return WatchQuery(brand=self.brand, model=self.model, reference=self.pricing_reference, year=self.year,
                          condition=self.condition, box_papers=self.box_papers, dial=self.dial,
                          bracelet=self.bracelet, metal=self.metal)


class SlotTakenError(Exception):
    def __init__(self, slot: int | None):
        super().__init__(f"Slot {slot} is already taken")
        self.slot = slot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | PathLike) -> sqlite3.Connection:
    # FastAPI may run a dependency and its endpoint on different threads; each
    # connection is still used by one request at a time.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for table, column, decl in MIGRATIONS:
        if column not in {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()
    return conn


def _write(conn: sqlite3.Connection, sql: str, params: tuple, slot: int | None, commit: bool = True) -> sqlite3.Cursor:
    try:
        cur = conn.execute(sql, params)
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            raise SlotTakenError(slot) from e
        raise
    if commit:
        conn.commit()
    return cur


def _watch(row: sqlite3.Row) -> Watch:
    return Watch(**dict(row))


def list_watches(conn: sqlite3.Connection) -> list[Watch]:
    return [_watch(r) for r in conn.execute(_SELECT + " ORDER BY w.slot IS NULL, w.slot, w.id")]


def get_watch(conn: sqlite3.Connection, watch_id: int) -> Watch | None:
    row = conn.execute(_SELECT + " WHERE w.id = ?", (watch_id,)).fetchone()
    return _watch(row) if row else None


def add_watch(conn, brand: str, model: str, reference: str, slot: int | None, nickname: str | None,
              price_reference: str | None = None, **details) -> int:
    d = DETAIL_DEFAULTS | details
    cur = _write(
        conn,
        "INSERT INTO watches (brand, model, reference, slot, nickname, created_at, price_reference,"
        " year, condition, box_papers, dial, bracelet, metal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (brand, model, reference, slot, nickname, now_iso(), price_reference,
         d["year"], d["condition"], d["box_papers"], d["dial"], d["bracelet"], d["metal"]),
        slot,
    )
    return cur.lastrowid


def clear_market_data(conn: sqlite3.Connection, watch_id: int) -> None:
    for table in ("prices", "comparables", "valuations"):
        conn.execute(f"DELETE FROM {table} WHERE watch_id = ?", (watch_id,))


def update_watch(conn, watch_id: int, brand: str, model: str, reference: str, slot: int | None, nickname: str | None,
                 price_reference: str | None = None, **details) -> None:
    d = DETAIL_DEFAULTS | details
    old = conn.execute("SELECT brand, model, reference, price_reference FROM watches WHERE id = ?",
                       (watch_id,)).fetchone()
    _write(
        conn,
        "UPDATE watches SET brand = ?, model = ?, reference = ?, slot = ?, nickname = ?, price_reference = ?,"
        " year = ?, condition = ?, box_papers = ?, dial = ?, bracelet = ?, metal = ? WHERE id = ?",
        (brand, model, reference, slot, nickname, price_reference,
         d["year"], d["condition"], d["box_papers"], d["dial"], d["bracelet"], d["metal"], watch_id),
        slot,
        commit=False,
    )
    if old:
        priced_as_changed = (old["brand"], old["reference"], old["price_reference"]) != (brand, reference,
                                                                                       price_reference)
        model_matters = not (price_reference or reference)  # without a reference, searches use the model
        if priced_as_changed or (model_matters and old["model"] != model):
            clear_market_data(conn, watch_id)
    conn.commit()


def delete_watch(conn: sqlite3.Connection, watch_id: int) -> None:
    conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
    conn.commit()


def add_price(conn: sqlite3.Connection, watch_id: int, result: PriceResult, fetched_at: str | None = None) -> None:
    conn.execute(
        "INSERT INTO prices (watch_id, price_usd, sample_size, source, fetched_at, price_date) VALUES (?, ?, ?, ?, ?, ?)",
        (watch_id, result.price_usd, result.sample_size, result.source, fetched_at or now_iso(), result.as_of),
    )
    conn.commit()


def replace_comparables(conn: sqlite3.Connection, watch_id: int, source: str, comps: list[Comparable],
                        fetched_at: str | None = None) -> None:
    stamp = fetched_at or now_iso()
    conn.execute("DELETE FROM comparables WHERE watch_id = ? AND source = ?", (watch_id, source))
    conn.executemany(
        f"INSERT INTO comparables (watch_id, {', '.join(COMPARABLE_COLUMNS)}, fetched_at)"
        f" VALUES (?, {', '.join('?' * len(COMPARABLE_COLUMNS))}, ?)",
        [(watch_id, c.source, c.kind, c.price_usd, c.date.isoformat() if c.date else None, c.title, c.url,
          c.reference, c.year, c.condition, c.box_papers, c.dial, c.bracelet, c.metal, int(c.best_offer), stamp)
         for c in comps],
    )
    conn.commit()


def load_comparables(conn: sqlite3.Connection, watch_id: int) -> list[Comparable]:
    rows = conn.execute("SELECT * FROM comparables WHERE watch_id = ? ORDER BY id", (watch_id,)).fetchall()
    return [Comparable(source=r["source"], kind=r["kind"], price_usd=r["price_usd"],
                       date=date.fromisoformat(r["date"]) if r["date"] else None, title=r["title"], url=r["url"],
                       reference=r["reference"], year=r["year"], condition=r["condition"],
                       box_papers=r["box_papers"], dial=r["dial"], bracelet=r["bracelet"], metal=r["metal"],
                       best_offer=bool(r["best_offer"])) for r in rows]


def add_valuation(conn: sqlite3.Connection, watch_id: int, v: Valuation, as_of: str | None = None) -> None:
    values = [getattr(v, name) for name in VALUATION_COLUMNS]
    conn.execute(
        f"INSERT INTO valuations (watch_id, {', '.join(VALUATION_COLUMNS)}, factors_json, failed_sources, as_of)"
        f" VALUES (?, {', '.join('?' * len(VALUATION_COLUMNS))}, ?, ?, ?)",
        (watch_id, *values, json.dumps(v.factors), ",".join(v.failed_sources), as_of or now_iso()),
    )
    conn.commit()


def _valuation_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["factors"] = json.loads(d.pop("factors_json"))
    d["failed_sources"] = tuple(s for s in d["failed_sources"].split(",") if s)
    return d


def latest_valuation(conn: sqlite3.Connection, watch_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM valuations WHERE watch_id = ? ORDER BY as_of DESC, id DESC LIMIT 1",
                       (watch_id,)).fetchone()
    return _valuation_dict(row) if row else None


def latest_valuations(conn: sqlite3.Connection) -> dict[int, dict]:
    rows = conn.execute("""
        SELECT * FROM valuations v WHERE v.id = (
            SELECT id FROM valuations WHERE watch_id = v.watch_id ORDER BY as_of DESC, id DESC LIMIT 1)
    """).fetchall()
    return {r["watch_id"]: _valuation_dict(r) for r in rows}


def latest_fetch_time(conn: sqlite3.Connection) -> str | None:
    return conn.execute(
        "SELECT MAX(t) FROM (SELECT MAX(fetched_at) AS t FROM prices UNION ALL SELECT MAX(as_of) FROM valuations)"
    ).fetchone()[0]
```

- [ ] **Step 4: Run the new tests and the whole suite**

Run: `server/.venv/bin/pytest server/tests -q`
Expected: all pass. That includes the 7 new tests in `test_db_valuation.py` and every existing test. Existing tests that call `add_watch`/`update_watch` positionally still work, because the detail arguments are keyword-only with defaults.

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/db.py server/tests/test_db_valuation.py
git commit -m "feat: store watch details, comparables and valuations"
```

---

### Task 9: Valuation service and wiring

**Files:**
- Create: `server/watchbox/valuation/service.py`
- Modify: `server/watchbox/refresh.py`, `server/watchbox/config.py`, `server/watchbox/providers.py`, `server/tests/test_providers.py`
- Test: `server/tests/test_val_service.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_val_service.py`:
```python
from datetime import date

import pytest

from watchbox import db, refresh
from watchbox.valuation.models import Comparable
from watchbox.valuation.service import ValuationService
from watchbox.valuation.sources.apify import SourceError


def comps(source, price=11000.0, n=6):
    kind = "sold" if source == "ebay" else "asking"
    return [Comparable(source=source, kind=kind, price_usd=price + i, date=date(2026, 9, 30),
                       title="Rolex Submariner Date 116610LN") for i in range(n)]


class FakeSource:
    def __init__(self, name, result):
        self.name, self.result, self.calls = name, result, 0

    def fetch(self, query):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_refresh_stores_comparables_and_a_valuation(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    service = ValuationService([FakeSource("ebay", comps("ebay")), FakeSource("chrono24", comps("chrono24", 12000))])
    assert refresh.refresh_watch(conn, service, db.get_watch(conn, wid))  # delegated by watchbox.refresh
    w = db.get_watch(conn, wid)
    assert w.price_source == "comps" and 10_000 < w.price_usd < 12_500
    assert len(db.load_comparables(conn, wid)) == 12


def test_one_failed_source_keeps_its_old_comparables_and_lowers_confidence(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    db.replace_comparables(conn, wid, "chrono24", comps("chrono24", 12000))
    service = ValuationService([FakeSource("ebay", comps("ebay", n=12)), FakeSource("chrono24", SourceError("x"))])
    assert service.refresh_watch(conn, db.get_watch(conn, wid))
    assert len(db.load_comparables(conn, wid)) == 18
    assert db.latest_valuation(conn, wid)["failed_sources"] == ("chrono24",)


def test_all_sources_failing_keeps_previous_valuation(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    good = ValuationService([FakeSource("ebay", comps("ebay"))])
    good.refresh_watch(conn, db.get_watch(conn, wid))
    before = db.get_watch(conn, wid).price_usd
    bad = ValuationService([FakeSource("ebay", SourceError("down"))])
    assert not bad.refresh_watch(conn, db.get_watch(conn, wid))
    assert db.get_watch(conn, wid).price_usd == before


def test_recompute_uses_stored_comparables_without_fetching(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)
    source = FakeSource("ebay", comps("ebay", 10000.0))
    service = ValuationService([source])
    service.refresh_watch(conn, db.get_watch(conn, wid))
    full_set = db.get_watch(conn, wid).price_usd
    db.update_watch(conn, wid, "Rolex", "Submariner Date", "116610LN", 1, None, box_papers="watch_only")
    assert service.recompute(conn, wid)
    assert source.calls == 1
    assert db.get_watch(conn, wid).price_usd < full_set


def test_result_is_discarded_if_watch_changes_during_fetch(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner Date", "116610LN", 1, None)

    class EditingSource(FakeSource):
        def fetch(self, query):
            db.update_watch(conn, wid, "Rolex", "Submariner Date", "126610LN", 1, None)
            return comps("ebay")

    assert not ValuationService([EditingSource("ebay", None)]).refresh_watch(conn, db.get_watch(conn, wid))
    assert db.load_comparables(conn, wid) == []
```

Append to `server/tests/test_providers.py`:
```python


def test_auto_prefers_comps_when_apify_token_set():
    from watchbox.valuation.service import ValuationService
    s = settings(apify_token="a", watchapi_token="t")
    assert isinstance(make_provider(s), ValuationService)
    assert isinstance(make_provider(settings(price_source="thewatchapi", watchapi_token="t", apify_token="a")),
                      TheWatchApiProvider)
```

In the same file, change the `settings()` helper's base dict to include `apify_token=""`:
```python
    base = dict(ebay_client_id="", ebay_client_secret="", refresh_hours=24, db_path="x.db",
                watchapi_token="", price_source="auto", apify_token="")
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_val_service.py server/tests/test_providers.py -q`
Expected: FAIL (`ModuleNotFoundError: ...service`, and `TypeError` for `apify_token`).

- [ ] **Step 3: Implement `server/watchbox/valuation/service.py`**

```python
"""Fetches comparables for a watch, stores them, and values the watch."""
import logging
import sqlite3

from .. import db
from .engine import value

log = logging.getLogger("watchbox.valuation")


class ValuationService:
    """A price "provider" for the app: it refreshes watches itself (see watchbox.refresh.refresh_watch)."""

    source = "comps"

    def __init__(self, sources: list):
        self._sources = list(sources)

    def refresh_watch(self, conn: sqlite3.Connection, watch: db.Watch) -> bool:
        query = watch.query
        fetched, failed = {}, []
        for source in self._sources:
            try:
                fetched[source.name] = source.fetch(query)
            except Exception as e:  # one source failing must not stop the other
                log.warning("%s failed for %s %s: %s", source.name, watch.brand, query.reference or watch.model, e)
                failed.append(source.name)
        if not fetched:
            return False
        current = db.get_watch(conn, watch.id)
        if current is None or current.identity != watch.identity:
            log.info("watch %s changed or was deleted during fetch; discarding result", watch.id)
            return False
        try:
            for name, comps in fetched.items():
                db.replace_comparables(conn, watch.id, name, comps)
        except sqlite3.Error:
            log.exception("failed to store comparables for watch %s", watch.id)
            return False
        return self._value_and_store(conn, current, tuple(failed))

    def recompute(self, conn: sqlite3.Connection, watch_id: int) -> bool:
        """Re-value from stored comparables, e.g. after the owner edits condition or box & papers."""
        watch = db.get_watch(conn, watch_id)
        if watch is None:
            return False
        last = db.latest_valuation(conn, watch_id)
        return self._value_and_store(conn, watch, last["failed_sources"] if last else ())

    def _value_and_store(self, conn: sqlite3.Connection, watch: db.Watch, failed: tuple[str, ...]) -> bool:
        valuation = value(watch.query, db.load_comparables(conn, watch.id),
                          estimated_reference=bool(watch.price_reference), failed_sources=failed)
        if valuation is None:
            log.warning("no usable comparables for watch %s (%s %s)", watch.id, watch.brand, watch.model)
            return False
        db.add_valuation(conn, watch.id, valuation)
        log.info("%s %s -> $%.0f (%s confidence, tier %d, %d eBay + %d Chrono24)", watch.brand,
                 watch.query.reference or watch.model, valuation.estimate_usd, valuation.confidence,
                 valuation.tier, valuation.n_ebay, valuation.n_c24)
        return True
```

- [ ] **Step 4: Delegate in `server/watchbox/refresh.py`**

At the very top of `refresh_watch`'s body, before `try:`, insert:
```python
    if hasattr(provider, "refresh_watch"):  # e.g. the valuation engine, which stores its own results
        return provider.refresh_watch(conn, watch)
```

- [ ] **Step 5: Config and provider selection**

In `server/watchbox/config.py`:
- Add the field `apify_token: str = ""` after `price_source`.
- Change the `price_source` comment to `# auto | comps | thewatchapi | ebay`.
- In `load_settings()`, add `apify_token=os.getenv("APIFY_TOKEN", "").strip(),` to the `Settings(...)` call.

Replace `server/watchbox/providers.py` with:
```python
"""Picks the price provider (PRICE_SOURCE=auto prefers the valuation engine, then TheWatchAPI, then eBay)."""
import logging

from .config import Settings
from .ebay import EbayBrowseProvider
from .pricing import PriceProvider
from .valuation.service import ValuationService
from .valuation.sources.apify import ApifyClient
from .valuation.sources.chrono24 import ApifyChrono24Source
from .valuation.sources.ebay_sold import ApifyEbaySoldSource
from .watchapi import TheWatchApiProvider

log = logging.getLogger("watchbox.providers")
SOURCES = ("comps", "thewatchapi", "ebay")


def make_provider(settings: Settings) -> PriceProvider | ValuationService | None:
    source = settings.price_source
    has_ebay = bool(settings.ebay_client_id and settings.ebay_client_secret)
    if source == "auto":
        source = ("comps" if settings.apify_token else "thewatchapi" if settings.watchapi_token
                  else "ebay" if has_ebay else "")
    if source == "comps" and settings.apify_token:
        client = ApifyClient(settings.apify_token)
        return ValuationService([ApifyEbaySoldSource(client), ApifyChrono24Source(client)])
    if source == "thewatchapi" and settings.watchapi_token:
        return TheWatchApiProvider(settings.watchapi_token)
    if source == "ebay" and has_ebay:
        return EbayBrowseProvider(settings.ebay_client_id, settings.ebay_client_secret)
    if source not in ("", *SOURCES):
        log.warning("unknown PRICE_SOURCE %r (use auto, comps, thewatchapi or ebay)", settings.price_source)
    else:
        log.warning("no price source key set (APIFY_TOKEN, THEWATCHAPI_TOKEN or EBAY_CLIENT_ID/SECRET);"
                    " prices will not update")
    return None
```

- [ ] **Step 6: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests -q`
Expected: all pass (5 new service tests and 1 new provider test).

- [ ] **Step 7: Commit**

```bash
git add server/watchbox/valuation/service.py server/watchbox/refresh.py server/watchbox/config.py server/watchbox/providers.py server/tests/test_val_service.py server/tests/test_providers.py
git commit -m "feat: valuation service wired in as the comps price source"
```

---

### Task 10: Web app and LCD

**Files:**
- Modify: `server/watchbox/app.py`, `server/watchbox/display.py`, `server/watchbox/templates/_form.html`, `server/watchbox/templates/index.html`, `server/watchbox/templates/base.html`
- Test: `server/tests/test_app_valuation.py`, plus one test appended to `server/tests/test_display.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_app_valuation.py`:
```python
import pytest
from fastapi.testclient import TestClient

from watchbox import db
from watchbox.app import create_app
from watchbox.config import Settings
from watchbox.valuation.models import Valuation


def val(estimate):
    return Valuation(estimate_usd=estimate, confidence="medium", tier=1, n_ebay=20, n_c24=8, ebay_median=11500.0,
                     ebay_p10=10500.0, ebay_p90=12900.0, ebay_min=9800.0, ebay_max=13300.0, c24_median=12400.0,
                     gap=0.07, w_ebay=0.7, w_c24=0.3, backtest_n=20, backtest_mdape=0.042, backtest_within10=0.9,
                     factors={})


class FakeService:
    source = "comps"

    def __init__(self):
        self.refreshed, self.recomputed = [], []

    def refresh_watch(self, conn, watch):
        self.refreshed.append(watch.id)
        db.add_valuation(conn, watch.id, val(11500.0))
        return True

    def recompute(self, conn, watch_id):
        self.recomputed.append(watch_id)
        db.add_valuation(conn, watch_id, val(9800.0))
        return True


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture
def client(tmp_path, service):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=24, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, service, run_scheduler=False)) as c:
        yield c


FORM = {"brand": "Rolex", "model": "Submariner Date", "reference": "116610LN", "slot": "4", "nickname": "",
        "price_reference": "", "year": "2015", "condition": "very_good", "box_papers": "full_set",
        "dial": "black", "bracelet": "oyster", "metal": "steel"}


def post(client, url, **changes):
    return client.post(url, data=FORM | changes, follow_redirects=False)


def test_details_are_saved_and_shown_in_the_edit_form(client):
    assert post(client, "/watches").status_code == 303
    page = client.get("/watches/1/edit").text
    assert 'value="very_good" selected' in page and 'value="black" selected' in page
    assert 'value="2015"' in page


def test_reference_is_optional(client):
    r = post(client, "/watches", reference="", brand="Glashütte Original", model="Sixties Panorama Date", slot="3")
    assert "error" not in r.headers["location"]


@pytest.mark.parametrize("field, bad", [("year", "1850"), ("year", "abc"), ("condition", "pristine"),
                                        ("dial", "purple")])
def test_invalid_details_are_rejected(client, field, bad):
    r = post(client, "/watches", **{field: bad})
    assert "error=" in r.headers["location"]


def test_breakdown_is_shown_on_the_index(client):
    post(client, "/watches")
    page = client.get("/").text
    assert "$11,500" in page
    assert "eBay sold (90 days): 20 sales" in page
    assert "Chrono24 asking: 8 listings" in page
    assert "within ±4.2%" in page
    assert "medium confidence" in page


def test_detail_edit_recomputes_without_refetching(client, service):
    post(client, "/watches")
    post(client, "/watches/1", condition="good")
    assert service.refreshed == [1] and service.recomputed == [1]
    assert "$9,800" in client.get("/").text


def test_reference_edit_refetches(client, service):
    post(client, "/watches")
    post(client, "/watches/1", reference="126610LN")
    assert service.refreshed == [1, 1] and service.recomputed == []
```

Append to `server/tests/test_display.py`:
```python


def test_low_confidence_prices_get_a_question_mark():
    low = Watch(id=1, brand="Rolex", model="Submariner", reference="X", slot=1, nickname=None,
                price_usd=11490.0, confidence="low")
    high = Watch(id=2, brand="Rolex", model="Datejust", reference="Y", slot=2, nickname=None,
                 price_usd=14420.0, confidence="high")
    screens = build_screens([low, high])
    assert screens[1]["line2"] == "$11,490?" and screens[2]["line2"] == "$14,420"
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_app_valuation.py server/tests/test_display.py -q`
Expected: FAIL (the form fields are ignored, there's no breakdown, and no `?`).

- [ ] **Step 3: Update `server/watchbox/display.py`**

Replace `price_line` with:
```python
def price_line(watch: Watch, today: date) -> str:
    if watch.price_usd is None:
        return "no price yet"
    price = ("~" if watch.price_reference else "") + format_price(watch.price_usd)
    if watch.confidence == "low" and len(price) < LCD_WIDTH:
        price += "?"
    label = as_of_label(watch.price_date, today)
    return f"{price} {label}" if label and len(price) + 1 + len(label) <= LCD_WIDTH else price
```

- [ ] **Step 4: Update `server/watchbox/app.py`**

1. Add these imports:
```python
from datetime import date

from .valuation.models import BOX_PAPERS, BRACELETS, CONDITIONS, DIALS, METALS, label
```

2. Replace the `SOURCE_LABELS` line with:
```python
SOURCE_LABELS = {"thewatchapi": "TheWatchAPI asking prices", "ebay": "median eBay asking price",
                 "comps": "estimated from eBay sales + Chrono24"}
```

3. Add these helpers after `validate_required`:
```python
def parse_year(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    this_year = date.today().year
    if not raw.isdigit() or not 1900 <= int(raw) <= this_year:
        raise ValueError(f"Year must be between 1900 and {this_year}")
    return int(raw)


def parse_choice(raw: str, allowed: tuple[str, ...], name: str, default: str | None = None) -> str | None:
    raw = raw.strip()
    if not raw:
        return default
    if raw not in allowed:
        raise ValueError(f"Unknown {name}: {raw}")
    return raw


def parse_details(year: str, condition: str, box_papers: str, dial: str, bracelet: str, metal: str) -> dict:
    return {
        "year": parse_year(year),
        "condition": parse_choice(condition, CONDITIONS, "condition", "excellent"),
        "box_papers": parse_choice(box_papers, BOX_PAPERS, "box & papers option", "full_set"),
        "dial": parse_choice(dial, DIALS, "dial color"),
        "bracelet": parse_choice(bracelet, BRACELETS, "bracelet"),
        "metal": parse_choice(metal, METALS, "case metal"),
    }
```

4. In `render(...)`, extend the context dict:
```python
        context |= {"format_price": format_price, "time_ago": time_ago, "slots": SLOTS,
                    "has_provider": provider is not None,
                    "source_label": SOURCE_LABELS.get(getattr(provider, "source", None), "asking prices"),
                    "label": label, "conditions": CONDITIONS, "box_papers_options": BOX_PAPERS, "dials": DIALS,
                    "bracelets": BRACELETS, "metals": METALS}
```

5. In `index`, pass the valuations: add `valuations=db.latest_valuations(conn),` to the `render(...)` call.

6. Replace the `create_watch` and `update_watch` handlers with:
```python
    @app.post("/watches")
    def create_watch(background: BackgroundTasks, conn: Conn, brand: FormStr, model: FormStr,
                     reference: FormStr = "", slot: FormStr = "", nickname: FormStr = "",
                     price_reference: FormStr = "", year: FormStr = "", condition: FormStr = "",
                     box_papers: FormStr = "", dial: FormStr = "", bracelet: FormStr = "", metal: FormStr = ""):
        try:
            validate_required(brand, model)
            if reference.strip():
                validate_reference(reference)
            if price_reference.strip():
                validate_reference(price_reference)
            details = parse_details(year, condition, box_papers, dial, bracelet, metal)
            watch_id = db.add_watch(conn, brand.strip(), model.strip(), reference.strip(), parse_slot(slot),
                                    nickname.strip() or None, price_reference.strip() or None, **details)
        except (ValueError, db.SlotTakenError) as e:
            return redirect("/", str(e))
        background.add_task(refresh_one, watch_id)
        return redirect("/")

    @app.post("/watches/{watch_id}")
    def update_watch(watch_id: int, background: BackgroundTasks, conn: Conn, brand: FormStr, model: FormStr,
                     reference: FormStr = "", slot: FormStr = "", nickname: FormStr = "",
                     price_reference: FormStr = "", year: FormStr = "", condition: FormStr = "",
                     box_papers: FormStr = "", dial: FormStr = "", bracelet: FormStr = "", metal: FormStr = ""):
        before = db.get_watch(conn, watch_id)
        if before is None:
            raise HTTPException(404, "Watch not found")
        try:
            validate_required(brand, model)
            if reference.strip():
                validate_reference(reference)
            if price_reference.strip():
                validate_reference(price_reference)
            details = parse_details(year, condition, box_papers, dial, bracelet, metal)
            db.update_watch(conn, watch_id, brand.strip(), model.strip(), reference.strip(), parse_slot(slot),
                            nickname.strip() or None, price_reference.strip() or None, **details)
        except (ValueError, db.SlotTakenError) as e:
            return redirect(f"/watches/{watch_id}/edit", str(e))
        after = db.get_watch(conn, watch_id)
        if before.identity != after.identity or not hasattr(provider, "recompute"):
            background.add_task(refresh_one, watch_id)
        else:
            provider.recompute(conn, watch_id)  # only details changed: re-value from stored comparables
        return redirect("/")
```

- [ ] **Step 5: Replace `server/watchbox/templates/_form.html` with:**

```html
<form method="post" action="{{ action }}" class="watch-form">
  <label>Brand <input name="brand" required value="{{ fw.brand if fw else '' }}" placeholder="Rolex"></label>
  <label>Model <input name="model" required value="{{ fw.model if fw else '' }}" placeholder="Submariner Date"></label>
  <label>Reference number (optional, best if you have it)
    <input name="reference" value="{{ fw.reference if fw else '' }}" placeholder="116610LN"></label>
  <label>Year (optional) <input name="year" inputmode="numeric" value="{{ fw.year if fw and fw.year else '' }}" placeholder="2015"></label>
  <label>Condition
    <select name="condition">
      {% for c in conditions %}<option value="{{ c }}" {% if (fw.condition if fw else 'excellent') == c %}selected{% endif %}>{{ label(c) }}</option>{% endfor %}
    </select>
  </label>
  <label>Box &amp; papers
    <select name="box_papers">
      {% for b in box_papers_options %}<option value="{{ b }}" {% if (fw.box_papers if fw else 'full_set') == b %}selected{% endif %}>{{ label(b) }}</option>{% endfor %}
    </select>
  </label>
  <label>Dial color (optional)
    <select name="dial"><option value="">Not set</option>
      {% for d in dials %}<option value="{{ d }}" {% if fw and fw.dial == d %}selected{% endif %}>{{ label(d) }}</option>{% endfor %}
    </select>
  </label>
  <label>Bracelet (optional)
    <select name="bracelet"><option value="">Not set</option>
      {% for b in bracelets %}<option value="{{ b }}" {% if fw and fw.bracelet == b %}selected{% endif %}>{{ label(b) }}</option>{% endfor %}
    </select>
  </label>
  <label>Case metal (optional)
    <select name="metal"><option value="">Not set</option>
      {% for m in metals %}<option value="{{ m }}" {% if fw and fw.metal == m %}selected{% endif %}>{{ label(m) }}</option>{% endfor %}
    </select>
  </label>
  <label>Slot
    <select name="slot">
      <option value="">No slot</option>
      {% for s in slots %}<option value="{{ s }}" {% if fw and fw.slot == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
  </label>
  <label>Nickname (optional) <input name="nickname" value="{{ (fw.nickname or '') if fw else '' }}" placeholder="Dad's Sub"></label>
  <label>Price using reference (optional)
    <input name="price_reference" value="{{ (fw.price_reference or '') if fw else '' }}" placeholder="a close variant, if yours isn't listed">
  </label>
  <button type="submit">{{ submit_label }}</button>
</form>
```

- [ ] **Step 6: Show the breakdown in `server/watchbox/templates/index.html`**

Immediately before the line `    <a href="/watches/{{ w.id }}/edit">Edit</a>`, insert:
```html
    {% set v = valuations.get(w.id) %}
    {% if v %}
    <div class="breakdown">
      <span class="badge {{ v.confidence }}">{{ v.confidence }} confidence</span>
      {% if v.n_ebay %}<div>eBay sold (90 days): {{ v.n_ebay }} sales · median {{ format_price(v.ebay_median) }} · typical {{ format_price(v.ebay_p10) }}–{{ format_price(v.ebay_p90) }} (low {{ format_price(v.ebay_min) }}, high {{ format_price(v.ebay_max) }})</div>{% endif %}
      {% if v.n_c24 %}<div>Chrono24 asking: {{ v.n_c24 }} listings · median {{ format_price(v.c24_median) }}</div>{% endif %}
      <div>{% if v.backtest_mdape is not none %}Backtest: typically within ±{{ (v.backtest_mdape * 100) | round(1) }}% of real sales ({{ v.backtest_n }} tested){% else %}Backtest: not enough sales yet{% endif %}</div>
      <div class="muted">Match tier {{ v.tier }}{% if v.failed_sources %} · unavailable this time: {{ v.failed_sources | join(", ") }}{% endif %} · {{ v.as_of[:10] }}</div>
    </div>
    {% endif %}
```

In `server/watchbox/templates/base.html`, add these CSS rules just before `</style>`:
```css
    .breakdown { grid-column: 2 / 4; font-size: 13px; color: var(--muted); display: grid; gap: 2px; }
    .badge { justify-self: start; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: var(--line); color: var(--ink); }
    .badge.high { background: #d6f2e3; color: #1f5f4a; }
    .badge.low { background: var(--warn); }
```

- [ ] **Step 7: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests -q`
Expected: all pass, including the 9 cases in `test_app_valuation.py` (counting parametrized cases) and the new display test.

- [ ] **Step 8: Commit**

```bash
git add server/watchbox/app.py server/watchbox/display.py server/watchbox/templates server/tests/test_app_valuation.py server/tests/test_display.py
git commit -m "feat: watch detail fields, valuation breakdown and instant recompute in the web app"
```

---

### Task 11: Check script, docs and config

**Files:**
- Create: `server/scripts/check_valuation.py`
- Modify: `server/.env.example`, `README.md`, `docs/superpowers/specs/2026-10-02-valuation-engine-design.md`

- [ ] **Step 1: Create `server/scripts/check_valuation.py`**

```python
"""Explain one watch's valuation: python scripts/check_valuation.py <watch id> [--fetch]   (run from server/)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watchbox import db  # noqa: E402
from watchbox.config import load_settings  # noqa: E402
from watchbox.providers import make_provider  # noqa: E402
from watchbox.valuation.engine import value  # noqa: E402
from watchbox.valuation.match import in_tier  # noqa: E402
from watchbox.valuation.parse import is_junk  # noqa: E402
from watchbox.valuation.service import ValuationService  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or not args[0].isdigit():
        sys.exit("usage: python scripts/check_valuation.py <watch id> [--fetch]")
    settings = load_settings()
    conn = db.connect(settings.db_path)
    watch = db.get_watch(conn, int(args[0]))
    if watch is None:
        sys.exit(f"no watch with id {args[0]}")
    if "--fetch" in sys.argv:
        provider = make_provider(settings)
        if not isinstance(provider, ValuationService):
            sys.exit("--fetch needs APIFY_TOKEN set (and PRICE_SOURCE auto or comps)")
        print("fetching comparables (takes a minute or two)...")
        provider.refresh_watch(conn, watch)
    q = watch.query
    comps = db.load_comparables(conn, watch.id)
    print(f"\n{watch.brand} {watch.model} {q.reference or '(no reference)'} | {q.condition}, {q.box_papers}, "
          f"year {q.year or '?'}, dial {q.dial or '?'}, bracelet {q.bracelet or '?'}, metal {q.metal or '?'}")
    print(f"{len(comps)} stored comparables\n")
    for c in sorted(comps, key=lambda c: (c.source, c.price_usd)):
        reason = ("junk" if is_junk(c.title, q.reference) else "best offer" if c.best_offer
                  else "tier 1" if in_tier(c, q, 1) else "tier 2" if in_tier(c, q, 2)
                  else "tier 3" if in_tier(c, q, 3) else "no match")
        print(f"  {c.source:<8} ${c.price_usd:>9,.0f}  {reason:<10} {c.box_papers or '-':<11} "
              f"{c.condition or '-':<9} {str(c.year or '-'):<5} {c.title[:60]}")
    last = db.latest_valuation(conn, watch.id)
    v = value(q, comps, estimated_reference=bool(watch.price_reference),
              failed_sources=last["failed_sources"] if last else ())
    if v is None:
        sys.exit("\nno usable comparables")
    print(f"\nESTIMATE ${v.estimate_usd:,.0f}  ({v.confidence} confidence, tier {v.tier})")
    if v.n_ebay:
        print(f"  eBay sold: {v.n_ebay} used, median ${v.ebay_median:,.0f}, typical ${v.ebay_p10:,.0f}-"
              f"${v.ebay_p90:,.0f}, range ${v.ebay_min:,.0f}-${v.ebay_max:,.0f}")
    if v.n_c24:
        print(f"  Chrono24 asking: {v.n_c24} used, median ${v.c24_median:,.0f}, asking-to-sold gap {v.gap:.1%}")
    print(f"  weights: eBay {v.w_ebay:.0%}, Chrono24 {v.w_c24:.0%}")
    print(f"  factors: box {v.factors['box']}, condition {v.factors['condition']}, "
          f"learned {v.factors['learned']}")
    if v.backtest_mdape is not None:
        print(f"  backtest: {v.backtest_n} sales, median error {v.backtest_mdape:.1%}, "
              f"{v.backtest_within10:.0%} within ±10%")
    else:
        print("  backtest: not enough sales")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-test the script offline**

Run (from `server/`), against a temporary DB:
```bash
cd server && DB_PATH=/tmp/wb_check.db .venv/bin/python -c "
from watchbox import db; from watchbox.valuation.sources import ebay_sold, chrono24; import json
c = db.connect('/tmp/wb_check.db'); wid = db.add_watch(c, 'Rolex', 'Submariner Date', '116610LN', 4, None, dial='black', metal='steel')
db.replace_comparables(c, wid, 'ebay', [x for x in map(ebay_sold.comparable_from_row, json.load(open('tests/fixtures/ebay_sold_116610ln.json'))) if x])
db.replace_comparables(c, wid, 'chrono24', [x for x in map(chrono24.comparable_from_row, json.load(open('tests/fixtures/chrono24_116610ln.json'))) if x])
print(wid)" && DB_PATH=/tmp/wb_check.db .venv/bin/python scripts/check_valuation.py 1 | tail -8; rm -f /tmp/wb_check.db
```
Expected: an `ESTIMATE $1x,xxx` line followed by eBay, Chrono24, weights, factors and backtest lines.

- [ ] **Step 3: Update `server/.env.example`**

Add these lines after the comment block at the top:
```text
# Most accurate: eBay sold (90 days) + Chrono24 asking prices via Apify (https://apify.com → Settings → API & Integrations).
APIFY_TOKEN=
```
Change the `PRICE_SOURCE` comment and line to:
```text
# auto = Apify valuation engine if APIFY_TOKEN is set, else TheWatchAPI, else eBay. Or force: comps | thewatchapi | ebay
PRICE_SOURCE=auto
```

- [ ] **Step 4: Update `README.md`**

Under "## Get a price source key", insert this as the first subsection:
```markdown
**Apify valuation engine (default, most accurate):** create a free account at https://apify.com, copy your Personal API token (Console → Settings → API & Integrations) into `server/.env` as `APIFY_TOKEN`. Each watch is valued from eBay sold listings (last 90 days) and Chrono24 asking prices, adjusted for its condition, box & papers and other details, with a backtest that shows how accurate the estimate is. Explain any watch's number with `.venv/bin/python scripts/check_valuation.py <watch id>` (add `--fetch` to pull fresh data first).
```

- [ ] **Step 5: Align the spec with the implementation**

In `docs/superpowers/specs/2026-10-02-valuation-engine-design.md`:
- In section 8, replace `c24_count, c24_median` with `c24_median`, and add `failed_sources` before `as_of` in the column list.
- In section 10, replace `refresh.py       # fetch, store comparables, run engine, store valuation` with `service.py       # ValuationService: fetch, store comparables, value, recompute`.
- In section 4, replace the year-preference sentence with: "Year: when the owner set a year, listings more than 3 years away are dropped, and listings with an unknown year are kept, provided at least 5 remain. Otherwise all are kept."
- In section 2 "Storage", replace "Each refresh **replaces** that watch's comparables. Rows older than 90 days are deleted." with "Each refresh replaces that watch's comparables **per source**, so a source that fails keeps its previous rows."

- [ ] **Step 6: Run the full suite**

Run: `server/.venv/bin/pytest server/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add server/scripts/check_valuation.py server/.env.example README.md docs/superpowers/specs/2026-10-02-valuation-engine-design.md
git commit -m "docs: valuation check script, config and README"
```

---

### Task 12: [CONTROLLER] Live acceptance

- [ ] **Step 1:** Restart the app: stop the running server, then start `cd server && .venv/bin/python -m watchbox` in the background. The log should show `Price source: comps`.
- [ ] **Step 2:** On the web page, set details for the owner's 4 watches. Ask the owner for their condition, box & papers and year, or leave the defaults.
- [ ] **Step 3:** For each watch, run `.venv/bin/python scripts/check_valuation.py <id> --fetch`. It costs a few cents of Apify credit per watch. Check that:
  - Every watch gets an estimate.
  - The 116610LN lands between about $11.5k and $12.3k for a full set in excellent condition.
  - Junk and best-offer rows are labelled.
  - The backtest is shown wherever there are 6 or more sales.
- [ ] **Step 4:** Edit one watch's box & papers on the web page and confirm the estimate changes immediately, with no new Apify run in the server log.
- [ ] **Step 5:** Confirm the LCD shows the new estimates within 60 s.
