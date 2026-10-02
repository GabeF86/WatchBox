"""Reads watch details out of listing titles and Chrono24 spec fields. Pure functions."""
import re
import unicodedata

from .models import DIALS

JUNK_PHRASES = (
    # accessories, not watches
    "box only", "papers only", "strap only", "bracelet only", "links only", "dial only", "bezel insert",
    "crown only", "case back", "instruction manual", "manual only", "booklet",
    # not working, not genuine, or not as the factory made it
    "for parts", "parts only", "for repair", "needs repair", "repair only", "replica", "homage",
    "custom", "aftermarket", "diamonds added", "aftermarket diamond", "iced", "pvd", "dlc",
)
FULL_SET_PHRASES = ("b&p", "b & p", "box and papers", "box & papers", "box/papers", "box papers",
                    "full set", "complete set")
YEAR_RE = re.compile(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)")
DIAL_RE = re.compile(r"(?<![a-z])(black|blue|white|silver|green|grey|gray|champagne|brown|red)\s+dial")
STRAP_RE = re.compile(r"(?<![a-z])(oyster|leather|rubber)\s+(bracelet|strap|band)")


def norm(text: str | None) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _has(text: str, phrase: str) -> bool:
    """Whole-word / whole-phrase match on already-lowercased text."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def is_junk(title: str | None) -> bool:
    t = (title or "").lower()
    return any(_has(t, p) for p in JUNK_PHRASES)


def reference_matches(reference: str | None, *texts: str | None) -> bool:
    ref = norm(reference)
    return bool(ref) and any(ref in norm(t) for t in texts if t)


def year_from_text(text: str | None) -> int | None:
    m = YEAR_RE.search(text or "")
    return int(m.group(1)) if m else None


def box_papers_from_title(title: str | None) -> str | None:
    t = (title or "").lower()
    if _has(t, "watch only") or (_has(t, "no box") and _has(t, "no papers")):
        return "watch_only"
    if any(_has(t, p) for p in FULL_SET_PHRASES):
        return "full_set"
    box = _has(t, "box") and not _has(t, "no box")
    papers = (_has(t, "papers") or _has(t, "card") or _has(t, "warranty")) and not _has(t, "no papers")
    if box and papers:
        return "full_set"
    if box:
        return "box_only"
    if papers:
        return "papers_only"
    return None


def condition_from_title(title: str | None) -> str | None:
    t = (title or "").lower()
    if _has(t, "like new") or _has(t, "mint"):
        return "excellent"
    if any(_has(t, p) for p in ("unworn", "nos", "brand new", "new old stock", "new")):
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

_C24_CONDITION = (  # order matters: "unworn" before "like new" before "new"; "very good" before "good"
    ("unworn", "new"), ("like new", "excellent"), ("mint", "excellent"), ("new", "new"),
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
