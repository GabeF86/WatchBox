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
    "dlc", "diamond", "diamonds", "sapphires", "gem set",
)
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


def is_junk(title: str | None) -> bool:
    t = (title or "").lower()
    return any(_has(t, p) for p in JUNK_PHRASES)


def reference_matches(reference: str | None, *texts: str | None) -> bool:
    """True if the reference appears in any text, tolerating spaces, dashes, dots and slashes inside it but not
    extra digits around it ("16610LN" must not match "116610LN")."""
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
        if any(n.startswith(("serv", "polish")) or n in ("sc", "rsc", "warranty") for n in neighbours):
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
    box = _has(t, "box") and not box_neg
    papers = (_has(t, "papers") and not _has(t, "no papers")) or (_has(t, "paper") and not _has(t, "no paper"))
    tokens = re.findall(r"[a-z0-9]+", t)
    if not papers and not _has(t, "no card"):
        for i, token in enumerate(tokens):
            if token != "card":
                continue
            near = tokens[max(0, i - 3):i] + tokens[i + 1:i + 4]
            prev = tokens[i - 1] if i else ""
            if prev in ("warranty", "rolex", "with") or any(n in ("box", "papers", "paper") for n in near):
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
