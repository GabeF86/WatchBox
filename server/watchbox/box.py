"""Structured collection data for the 3.5" display box (GET /api/box).

Everything is ready to draw: ASCII strings (the box's fonts have no accents), whole-dollar integers, and
local-time labels (the box has no clock).
"""
import unicodedata
from datetime import datetime, timezone, tzinfo

from .db import Watch
from .valuation.models import label

SLOT_COUNT = 8
BOX_SHORT = {"full_set": "Full set", "box_only": "Box only", "papers_only": "Papers only", "watch_only": "Watch only"}


def ascii(text: str | None) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def local_label(iso: str | None, tz: tzinfo | None = None) -> str:
    """'Oct 2, 1:14 PM' in the server's local time (or `tz`)."""
    if not iso:
        return ""
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t = t.astimezone(tz)
    return f"{t.strftime('%b')} {t.day}, {t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _money(value: float | None) -> int | None:
    return None if value is None else int(value + 0.5)


def _watch(w: Watch, v: dict | None, tz: tzinfo | None) -> dict:
    as_of = v["as_of"] if v else w.fetched_at
    return {
        "id": w.id,
        "name": ascii(w.nickname or w.model),
        "brand": ascii(w.brand),
        "model": ascii(w.model),
        "reference": ascii(w.reference),
        "details": f"{BOX_SHORT.get(w.box_papers, label(w.box_papers))}, {label(w.condition)}",
        "estimate_usd": _money(v["estimate_usd"] if v else w.price_usd),
        "estimated_reference": bool(w.price_reference),
        "confidence": v["confidence"] if v else None,
        "ebay": {"n": v["n_ebay"] if v else 0, "median": _money(v["ebay_median"] if v else None),
                 "p10": _money(v["ebay_p10"] if v else None), "p90": _money(v["ebay_p90"] if v else None)},
        "chrono24": {"n": v["n_c24"] if v else 0, "median": _money(v["c24_median"] if v else None)},
        "accuracy": {"n": v["backtest_n"] if v else 0,
                     "mdape": round(v["backtest_mdape"], 4) if v and v["backtest_mdape"] is not None else None},
        "as_of": as_of,
        "as_of_label": local_label(as_of, tz),
    }


def build_box_payload(watches: list[Watch], valuations: dict[int, dict], generated_at: str,
                      tz: tzinfo | None = None) -> dict:
    entries = {w.id: _watch(w, valuations.get(w.id), tz) for w in watches}
    by_slot = {w.slot: entries[w.id] for w in watches if w.slot is not None}
    priced = [e for e in entries.values() if e["estimate_usd"] is not None]
    newest = max((e["as_of"] for e in priced if e["as_of"]), default=None)
    return {
        "generated_at": generated_at,
        "total_usd": sum(e["estimate_usd"] for e in priced),
        "priced": len(priced),
        "updated_label": local_label(newest, tz),
        "slots": [{"slot": n, "watch": by_slot.get(n)} for n in range(1, SLOT_COUNT + 1)],
        "unslotted": [entries[w.id] for w in watches if w.slot is None],
    }
