"""Fetches prices for watches and stores them; failures never raise."""
import logging
import sqlite3
from datetime import datetime, timedelta

from . import db
from .pricing import PriceProvider

log = logging.getLogger("watchbox.refresh")


def refresh_watch(conn: sqlite3.Connection, provider: PriceProvider, watch: db.Watch) -> bool:
    try:
        result = provider.get_price(watch.brand, watch.pricing_reference)
    except Exception:
        log.exception("price fetch failed for %s %s", watch.brand, watch.pricing_reference)
        return False
    if result is None:
        log.warning("not enough listings for %s %s", watch.brand, watch.pricing_reference)
        return False
    current = db.get_watch(conn, watch.id)
    if current is None or (current.brand, current.pricing_reference) != (watch.brand, watch.pricing_reference):
        log.info("watch %s changed or was deleted during fetch; discarding result", watch.id)
        return False
    try:
        db.add_price(conn, watch.id, result)
    except sqlite3.Error:
        log.exception("failed to store price for %s %s", watch.brand, watch.pricing_reference)
        return False
    log.info("%s %s -> $%.0f (%d listings)", watch.brand, watch.pricing_reference, result.price_usd, result.sample_size)
    return True


def refresh_all(conn: sqlite3.Connection, provider: PriceProvider) -> int:
    return sum(refresh_watch(conn, provider, w) for w in db.list_watches(conn))


def needs_refresh(last_fetch_iso: str | None, refresh_hours: float, now: datetime) -> bool:
    if last_fetch_iso is None:
        return True
    return now - datetime.fromisoformat(last_fetch_iso) >= timedelta(hours=refresh_hours)
