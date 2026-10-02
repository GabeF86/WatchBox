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
