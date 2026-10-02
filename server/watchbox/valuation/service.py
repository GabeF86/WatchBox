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
