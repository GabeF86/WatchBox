"""SQLite storage for watches and their price history."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from os import PathLike

from .pricing import PriceResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    reference TEXT NOT NULL,
    slot INTEGER UNIQUE CHECK (slot BETWEEN 1 AND 8),
    nickname TEXT,
    created_at TEXT NOT NULL,
    price_reference TEXT
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
"""

_SELECT = """
SELECT w.id, w.brand, w.model, w.reference, w.slot, w.nickname, w.price_reference,
       p.price_usd, p.sample_size, p.fetched_at, p.source AS price_source, p.price_date
FROM watches w
LEFT JOIN prices p ON p.id = (
    SELECT id FROM prices WHERE watch_id = w.id ORDER BY fetched_at DESC, id DESC LIMIT 1
)
"""


@dataclass
class Watch:
    id: int
    brand: str
    model: str
    reference: str
    slot: int | None
    nickname: str | None
    price_reference: str | None = None  # look prices up under this reference instead (an estimate)
    price_usd: float | None = None
    sample_size: int | None = None
    fetched_at: str | None = None
    price_source: str | None = None
    price_date: str | None = None

    @property
    def pricing_reference(self) -> str:
        return self.price_reference or self.reference


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
    # Databases created before these columns existed.
    _add_column_if_missing(conn, "prices", "price_date")
    _add_column_if_missing(conn, "watches", "price_reference")
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str) -> None:
    if column not in {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")


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


def list_watches(conn: sqlite3.Connection) -> list[Watch]:
    rows = conn.execute(_SELECT + " ORDER BY w.slot IS NULL, w.slot, w.id").fetchall()
    return [Watch(**dict(r)) for r in rows]


def get_watch(conn: sqlite3.Connection, watch_id: int) -> Watch | None:
    row = conn.execute(_SELECT + " WHERE w.id = ?", (watch_id,)).fetchone()
    return Watch(**dict(row)) if row else None


def add_watch(conn, brand: str, model: str, reference: str, slot: int | None, nickname: str | None,
              price_reference: str | None = None) -> int:
    cur = _write(
        conn,
        "INSERT INTO watches (brand, model, reference, slot, nickname, created_at, price_reference)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (brand, model, reference, slot, nickname, now_iso(), price_reference),
        slot,
    )
    return cur.lastrowid


def update_watch(conn, watch_id: int, brand: str, model: str, reference: str, slot: int | None, nickname: str | None,
                 price_reference: str | None = None) -> None:
    old = conn.execute("SELECT brand, reference, price_reference FROM watches WHERE id = ?", (watch_id,)).fetchone()
    _write(
        conn,
        "UPDATE watches SET brand = ?, model = ?, reference = ?, slot = ?, nickname = ?, price_reference = ? WHERE id = ?",
        (brand, model, reference, slot, nickname, price_reference, watch_id),
        slot,
        commit=False,
    )
    if old and (old["brand"], old["reference"], old["price_reference"]) != (brand, reference, price_reference):
        conn.execute("DELETE FROM prices WHERE watch_id = ?", (watch_id,))
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


def latest_fetch_time(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MAX(fetched_at) FROM prices").fetchone()[0]
