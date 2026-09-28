"""Turns watches into short, ready-to-show lines for the 16x2 LCD."""
from datetime import datetime, timezone

from .db import Watch

LCD_WIDTH = 16


def fit(text: str) -> str:
    """ASCII only (the LCD can't draw accents), cut to one LCD line."""
    return text.encode("ascii", "ignore").decode()[:LCD_WIDTH]


def format_price(value: float) -> str:
    text = f"${value:,.0f}"
    if len(text) > 9:
        text = f"${value / 1_000_000:.1f}M"
    return text


def time_ago(iso: str | None, now: datetime | None = None) -> str:
    if not iso:
        return "never"
    now = now or datetime.now(timezone.utc)
    then = datetime.fromisoformat(iso)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    seconds = (now - then).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h ago"
    return f"{int(seconds // 86400)} d ago"


def display_name(watch: Watch) -> str:
    name = watch.nickname or watch.model
    return f"{watch.slot} {name}" if watch.slot is not None else name


def build_screens(watches: list[Watch]) -> list[dict[str, str]]:
    if not watches:
        return [{"line1": "No watches yet", "line2": "Add on the app"}]
    ordered = sorted(watches, key=lambda w: (w.slot is None, w.slot or 0, w.id))
    priced = [w for w in ordered if w.price_usd is not None]
    noun = "watch" if len(priced) == 1 else "watches"
    screens = [{
        "line1": fit(f"TOTAL {len(priced)} {noun}"),
        "line2": fit(format_price(sum(w.price_usd for w in priced))),
    }]
    for watch in ordered:
        price = format_price(watch.price_usd) if watch.price_usd is not None else "no price yet"
        screens.append({"line1": fit(display_name(watch)), "line2": fit(price)})
    return screens
