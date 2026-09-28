# WatchBox Prototype v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web app on the Mac stores watches and fetches eBay prices. The kit ESP32 pulls ready-to-show lines from it and cycles them on a 16×2 I2C LCD. Both parts live in a 3D-printed enclosure.

**Architecture:** A Python FastAPI app with SQLite owns all logic. It holds watches and price history, fetches prices through a swappable `PriceProvider` (eBay Browse API), and formats 16-character LCD lines. The ESP32 firmware is a thin client that fetches `GET /api/display` every 60 s and shows each screen for 4 s. The enclosure is a parametric OpenSCAD file exported to two STLs for Bambu Studio.

**Tech Stack:** Python 3.13, FastAPI, Jinja2, httpx, SQLite (stdlib), pytest · Arduino C++ via arduino-cli (esp32 core, LiquidCrystal_I2C, ArduinoJson 7) · OpenSCAD.

**Spec:** `docs/superpowers/specs/2026-09-27-watchbox-prototype-v0-design.md`

**Conventions:**
- Run every command from the repo root unless a step says otherwise.
- Steps marked **[USER]** need the physical hardware or the user's accounts. An agent stops at them and asks the user.

---

## File map

```
server/
  requirements.txt          # Python deps
  pytest.ini                # pytest config (pythonpath=.)
  .env.example              # EBAY_CLIENT_ID, EBAY_CLIENT_SECRET, REFRESH_HOURS, PORT, DB_PATH
  watchbox/
    __init__.py
    __main__.py             # `python -m watchbox`: builds provider, prints LAN URL, runs uvicorn
    config.py               # Settings dataclass + load_settings() from .env
    pricing.py              # PriceResult, PriceProvider protocol, junk/ref filtering, median
    db.py                   # SQLite schema, Watch dataclass, CRUD, price history
    display.py              # format_price, fit (16 chars), time_ago, build_screens
    ebay.py                 # EbayBrowseProvider (OAuth token cache + search)
    refresh.py              # refresh_watch / refresh_all / needs_refresh
    app.py                  # create_app(): HTML pages, form handlers, /api/display, scheduler
    templates/
      base.html             # layout + CSS
      index.html            # list, total, add form, refresh button
      edit.html             # edit + delete
      _form.html            # shared watch form
  scripts/
    check_price.py          # manual eBay sanity check for one reference
  tests/
    fixtures/ebay_search_126610ln.json
    test_pricing.py
    test_db.py
    test_display.py
    test_ebay.py
    test_refresh.py
    test_app.py
firmware/
  i2c_scan/i2c_scan.ino     # prints LCD I2C address
  watchbox_v0/
    watchbox_v0.ino         # main firmware
    config.example.h        # committed template
    config.h                # gitignored, user's Wi-Fi + server URL
enclosure/
  watchbox_v0.scad          # parametric enclosure (part = front | back | assembly)
README.md                   # how to run everything
```

---

### Task 1: Server scaffolding

**Files:**
- Create: `server/requirements.txt`, `server/pytest.ini`, `server/watchbox/__init__.py`, `server/tests/__init__.py`

- [ ] **Step 1: Create `server/requirements.txt`**

```text
fastapi>=0.115
uvicorn>=0.30
jinja2>=3.1
python-multipart>=0.0.9
httpx>=0.27
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 2: Create `server/pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 3: Create empty package files**

`server/watchbox/__init__.py` and `server/tests/__init__.py` are both empty files.

- [ ] **Step 4: Create the virtualenv and install**

Run:
```bash
python3 -m venv server/.venv && server/.venv/bin/pip install -q -r server/requirements.txt
```
Expected: exits 0.

- [ ] **Step 5: Verify pytest runs**

Run: `server/.venv/bin/pytest server/tests -q`
Expected: `no tests ran` (exit code 5 is fine here).

- [ ] **Step 6: Commit**

```bash
git add server/requirements.txt server/pytest.ini server/watchbox/__init__.py server/tests/__init__.py
git commit -m "chore: scaffold WatchBox server"
```

---

### Task 2: Pricing core (filtering + median)

**Files:**
- Create: `server/watchbox/pricing.py`
- Test: `server/tests/test_pricing.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_pricing.py`:
```python
from watchbox.pricing import PriceResult, filter_listings, is_junk, listing_matches, summarize_prices


def test_is_junk_flags_accessory_listings():
    assert is_junk("Rolex Submariner 126610LN BOX ONLY")
    assert is_junk("Homage Submariner 126610LN style automatic")
    assert is_junk("Rolex 126610LN bezel insert black")


def test_is_junk_keeps_normal_titles():
    assert not is_junk("Rolex Submariner Date 126610LN Black Ceramic Bezel 2023")
    assert not is_junk("Rolex 126610LN Oyster bracelet full set")


def test_listing_matches_reference_ignoring_spacing_and_case():
    assert listing_matches("Rolex Submariner 126610 LN 2022", "126610LN")
    assert listing_matches("omega speedmaster 310.30.42.50.01.001", "310304250 01001")
    assert not listing_matches("Rolex Submariner 124060", "126610LN")


def test_filter_listings_keeps_matching_non_junk_prices():
    listings = [
        ("Rolex Submariner 126610 LN 2022", 13000.0),
        ("Rolex Submariner 124060", 9500.0),
        ("Rolex 126610LN box only", 900.0),
    ]
    assert filter_listings(listings, "126610LN") == [13000.0]


def test_summarize_returns_median_after_outlier_removal():
    prices = [12000.0, 13000.0, 13500.0, 14000.0, 60000.0, 1000.0]
    listings = [(f"Rolex 126610LN #{i}", p) for i, p in enumerate(prices)]
    # median of all six = 13250 -> keep [6625, 26500] -> 12000, 13000, 13500, 14000 -> median 13250
    assert summarize_prices(listings, "126610LN", "ebay") == PriceResult(price_usd=13250.0, sample_size=4, source="ebay")


def test_summarize_needs_at_least_three_listings():
    listings = [("Rolex 126610LN", 13000.0), ("Rolex 126610LN", 13500.0)]
    assert summarize_prices(listings, "126610LN", "ebay") is None


def test_summarize_returns_none_when_outlier_removal_leaves_too_few():
    # 3 listings pass the reference/junk filter, but the 0.5x-2x band around
    # the median of [100, 100, 100000] (100) only keeps the two 100s.
    listings = [("Rolex 126610LN #1", 100.0), ("Rolex 126610LN #2", 100.0), ("Rolex 126610LN #3", 100000.0)]
    assert summarize_prices(listings, "126610LN", "ebay") is None


def test_listing_matches_returns_false_for_empty_reference():
    assert listing_matches("Rolex Submariner", "") is False
    assert listing_matches("Rolex Submariner", "-") is False


def test_is_junk_manual_and_repair_refinements():
    assert not is_junk("Omega Speedmaster Professional Manual Wind 310.30.42.50.01.001")
    assert is_junk("Rolex instruction manual 126610LN")
    assert is_junk("Rolex 126610LN needs repair")
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_pricing.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.pricing'`

- [ ] **Step 3: Implement `server/watchbox/pricing.py`**

```python
"""Price provider interface and the provider-independent price math."""
import re
from dataclasses import dataclass
from statistics import median
from typing import Protocol

MIN_SAMPLES = 3

JUNK_PHRASES = (
    "box only", "papers only", "empty box", "strap only", "bracelet only", "band only",
    "links only", "dial only", "bezel only", "bezel insert", "crown only", "case back",
    "for parts", "parts only", "for repair", "needs repair", "repair only", "homage", "replica",
    "instruction manual", "manual only", "booklet",
)


@dataclass(frozen=True)
class PriceResult:
    price_usd: float
    sample_size: int
    source: str


class PriceProvider(Protocol):
    def get_price(self, brand: str, reference: str) -> PriceResult | None: ...


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def is_junk(title: str) -> bool:
    lowered = title.lower()
    return any(phrase in lowered for phrase in JUNK_PHRASES)


def listing_matches(title: str, reference: str) -> bool:
    norm_reference = _norm(reference)
    if not norm_reference:
        return False
    return norm_reference in _norm(title) and not is_junk(title)


def filter_listings(listings: list[tuple[str, float]], reference: str) -> list[float]:
    return [price for title, price in listings if listing_matches(title, reference)]


def summarize_prices(listings: list[tuple[str, float]], reference: str, source: str) -> PriceResult | None:
    prices = filter_listings(listings, reference)
    if len(prices) < MIN_SAMPLES:
        return None
    mid = median(prices)
    kept = [p for p in prices if 0.5 * mid <= p <= 2 * mid]
    if len(kept) < MIN_SAMPLES:
        return None
    return PriceResult(price_usd=round(median(kept), 2), sample_size=len(kept), source=source)
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_pricing.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/pricing.py server/tests/test_pricing.py
git commit -m "feat: price filtering and median summary"
```

---

### Task 3: SQLite storage

**Files:**
- Create: `server/watchbox/db.py`
- Test: `server/tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_db.py`:
```python
import pytest

from watchbox import db
from watchbox.pricing import PriceResult


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_add_and_list_uses_latest_price(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"), fetched_at="2026-09-27T10:00:00+00:00")
    db.add_price(conn, wid, PriceResult(13400.0, 22, "ebay"), fetched_at="2026-09-27T16:00:00+00:00")
    [w] = db.list_watches(conn)
    assert (w.id, w.model, w.slot, w.price_usd, w.sample_size) == (wid, "Submariner", 1, 13400.0, 22)
    assert db.latest_fetch_time(conn) == "2026-09-27T16:00:00+00:00"


def test_list_orders_by_slot_with_unslotted_last(conn):
    db.add_watch(conn, "Cartier", "Tank Must", "WSTA0041", None, None)
    db.add_watch(conn, "Omega", "Speedmaster", "310.30.42.50.01.001", 2, None)
    db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    assert [w.model for w in db.list_watches(conn)] == ["Submariner", "Speedmaster", "Tank Must"]


def test_slot_must_be_unique(conn):
    db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    with pytest.raises(db.SlotTakenError, match="Slot 1 is already taken"):
        db.add_watch(conn, "Omega", "Speedmaster", "310.30.42.50.01.001", 1, None)


def test_update_keeps_prices_when_reference_unchanged(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.update_watch(conn, wid, "Rolex", "Submariner Date", "126610LN", 2, "Sub")
    w = db.get_watch(conn, wid)
    assert (w.model, w.slot, w.nickname, w.price_usd) == ("Submariner Date", 2, "Sub", 13000.0)


def test_update_clears_prices_when_reference_changes(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.update_watch(conn, wid, "Rolex", "GMT-Master II", "126710BLRO", 1, None)
    assert db.get_watch(conn, wid).price_usd is None


def test_update_clears_prices_when_only_brand_changes(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.update_watch(conn, wid, "Tudor", "Submariner", "126610LN", 1, None)
    assert db.get_watch(conn, wid).price_usd is None


def test_delete_removes_watch_and_prices(conn):
    wid = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    db.add_price(conn, wid, PriceResult(13000.0, 20, "ebay"))
    db.delete_watch(conn, wid)
    assert db.list_watches(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0


def test_get_missing_watch_returns_none(conn):
    assert db.get_watch(conn, 999) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_db.py -q`
Expected: FAIL, `ImportError: cannot import name 'db'`

- [ ] **Step 3: Implement `server/watchbox/db.py`**

```python
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
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    price_usd REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""

_SELECT = """
SELECT w.id, w.brand, w.model, w.reference, w.slot, w.nickname,
       p.price_usd, p.sample_size, p.fetched_at
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
    price_usd: float | None = None
    sample_size: int | None = None
    fetched_at: str | None = None


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


def list_watches(conn: sqlite3.Connection) -> list[Watch]:
    rows = conn.execute(_SELECT + " ORDER BY w.slot IS NULL, w.slot, w.id").fetchall()
    return [Watch(**dict(r)) for r in rows]


def get_watch(conn: sqlite3.Connection, watch_id: int) -> Watch | None:
    row = conn.execute(_SELECT + " WHERE w.id = ?", (watch_id,)).fetchone()
    return Watch(**dict(row)) if row else None


def add_watch(conn, brand: str, model: str, reference: str, slot: int | None, nickname: str | None) -> int:
    cur = _write(
        conn,
        "INSERT INTO watches (brand, model, reference, slot, nickname, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (brand, model, reference, slot, nickname, now_iso()),
        slot,
    )
    return cur.lastrowid


def update_watch(conn, watch_id: int, brand: str, model: str, reference: str, slot: int | None, nickname: str | None) -> None:
    old = conn.execute("SELECT brand, reference FROM watches WHERE id = ?", (watch_id,)).fetchone()
    _write(
        conn,
        "UPDATE watches SET brand = ?, model = ?, reference = ?, slot = ?, nickname = ? WHERE id = ?",
        (brand, model, reference, slot, nickname, watch_id),
        slot,
        commit=False,
    )
    if old and (old["brand"], old["reference"]) != (brand, reference):
        conn.execute("DELETE FROM prices WHERE watch_id = ?", (watch_id,))
    conn.commit()


def delete_watch(conn: sqlite3.Connection, watch_id: int) -> None:
    conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
    conn.commit()


def add_price(conn: sqlite3.Connection, watch_id: int, result: PriceResult, fetched_at: str | None = None) -> None:
    conn.execute(
        "INSERT INTO prices (watch_id, price_usd, sample_size, source, fetched_at) VALUES (?, ?, ?, ?, ?)",
        (watch_id, result.price_usd, result.sample_size, result.source, fetched_at or now_iso()),
    )
    conn.commit()


def latest_fetch_time(conn: sqlite3.Connection) -> str | None:
    return conn.execute("SELECT MAX(fetched_at) FROM prices").fetchone()[0]
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_db.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/db.py server/tests/test_db.py
git commit -m "feat: SQLite storage for watches and price history"
```

---

### Task 4: LCD display formatting

**Files:**
- Create: `server/watchbox/display.py`
- Test: `server/tests/test_display.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_display.py`:
```python
from datetime import datetime, timezone

from watchbox.db import Watch
from watchbox.display import build_screens, fit, format_price, time_ago


def w(id, model, slot=None, price=None, nickname=None):
    return Watch(id=id, brand="Rolex", model=model, reference="X", slot=slot, nickname=nickname, price_usd=price)


def test_format_price_whole_dollars_with_commas():
    assert format_price(13400.4) == "$13,400"
    assert format_price(999_999) == "$999,999"


def test_format_price_switches_to_millions_when_too_long():
    assert format_price(1_234_567) == "$1.2M"
    assert format_price(999_999.6) == "$1.0M"


def test_fit_truncates_to_16_ascii_chars():
    assert fit("1 Royal Oak Offshore Chronograph") == "1 Royal Oak Offs"
    assert fit("Café Racer") == "Caf Racer"


def test_fit_leaves_exactly_16_chars_unchanged():
    text = "1234567890123456"
    assert len(text) == 16
    assert fit(text) == text


def test_empty_collection():
    assert build_screens([]) == [{"line1": "No watches yet", "line2": "Add on the app"}]


def test_total_first_then_slots_in_order_unslotted_last():
    watches = [
        w(1, "Tank Must", slot=None, price=2600),
        w(2, "Speedmaster", slot=2, price=6150),
        w(3, "Submariner", slot=1, price=13400),
        w(4, "Nautilus", slot=3),
    ]
    assert build_screens(watches) == [
        {"line1": "TOTAL 3 watches", "line2": "$22,150"},
        {"line1": "1 Submariner", "line2": "$13,400"},
        {"line1": "2 Speedmaster", "line2": "$6,150"},
        {"line1": "3 Nautilus", "line2": "no price yet"},
        {"line1": "Tank Must", "line2": "$2,600"},
    ]


def test_nickname_wins_and_total_is_singular():
    assert build_screens([w(1, "Submariner", slot=5, price=100, nickname="Dad's Sub")]) == [
        {"line1": "TOTAL 1 watch", "line2": "$100"},
        {"line1": "5 Dad's Sub", "line2": "$100"},
    ]


def test_time_ago():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert time_ago(None, now) == "never"
    assert time_ago("2026-09-27T11:59:30+00:00", now) == "just now"
    assert time_ago("2026-09-27T11:15:00+00:00", now) == "45 min ago"
    assert time_ago("2026-09-27T06:00:00+00:00", now) == "6 h ago"
    assert time_ago("2026-09-24T12:00:00+00:00", now) == "3 d ago"


def test_time_ago_treats_naive_timestamp_as_utc():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert time_ago("2026-09-27T11:15:00", now) == "45 min ago"
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_display.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.display'`

- [ ] **Step 3: Implement `server/watchbox/display.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_display.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/display.py server/tests/test_display.py
git commit -m "feat: LCD screen formatting"
```

---

### Task 5: eBay Browse API provider

**Files:**
- Create: `server/watchbox/ebay.py`, `server/tests/fixtures/ebay_search_126610ln.json`
- Test: `server/tests/test_ebay.py`

- [ ] **Step 1: Create the fixture `server/tests/fixtures/ebay_search_126610ln.json`**

This is handcrafted data in the shape of the Browse API `item_summary/search` response.
```json
{
  "total": 8,
  "itemSummaries": [
    {"itemId": "v1|1|0", "title": "Rolex Submariner Date 126610LN Black Ceramic 2022 Box Papers", "price": {"value": "13000.00", "currency": "USD"}},
    {"itemId": "v1|2|0", "title": "Rolex Submariner 126610 LN 41mm Oystersteel", "price": {"value": "13500.00", "currency": "USD"}},
    {"itemId": "v1|3|0", "title": "2023 Rolex Submariner Date 126610LN Unworn", "price": {"value": "14000.00", "currency": "USD"}},
    {"itemId": "v1|4|0", "title": "Rolex 126610LN Submariner Full Set", "price": {"value": "12000.00", "currency": "USD"}},
    {"itemId": "v1|5|0", "title": "Rolex 126610LN box only", "price": {"value": "950.00", "currency": "USD"}},
    {"itemId": "v1|6|0", "title": "Rolex Submariner 126610LN Diamond Custom Iced", "price": {"value": "60000.00", "currency": "USD"}},
    {"itemId": "v1|7|0", "title": "Rolex Submariner 124060 No Date", "price": {"value": "9800.00", "currency": "USD"}},
    {"itemId": "v1|8|0", "title": "Rolex 126610LN Submariner", "price": {"value": "11000.00", "currency": "GBP"}}
  ]
}
```
Expected math: USD, reference match and not junk leaves 13000, 13500, 14000, 12000 and 60000. The median is 13500, so the keep range is [6750, 27000], which drops 60000. The median of [12000, 13000, 13500, 14000] is **13250**, from **4** listings.

- [ ] **Step 2: Write the failing tests**

`server/tests/test_ebay.py`:
```python
import json
from pathlib import Path

import httpx
import pytest

from watchbox.ebay import TOKEN_URL, EbayBrowseProvider, EbayError

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "ebay_search_126610ln.json").read_text())


def make_provider(handler, clock=lambda: 0.0):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return EbayBrowseProvider("id", "secret", http=http, clock=clock)


def token_response(token="tok"):
    return httpx.Response(200, json={"access_token": token, "expires_in": 7200})


def test_get_price_authenticates_searches_and_summarizes():
    def handler(request):
        if str(request.url).startswith(TOKEN_URL):
            assert request.headers["Authorization"].startswith("Basic ")
            assert "grant_type=client_credentials" in request.content.decode()
            return token_response()
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_US"
        assert request.url.params["q"] == "Rolex 126610LN"
        assert request.url.params["category_ids"] == "31387"
        assert request.url.params["filter"]
        assert request.url.params["limit"]
        return httpx.Response(200, json=FIXTURE)

    result = make_provider(handler).get_price("Rolex", "126610LN")
    assert (result.price_usd, result.sample_size, result.source) == (13250.0, 4, "ebay")


def test_search_skips_non_usd_prices():
    def handler(request):
        return token_response() if str(request.url).startswith(TOKEN_URL) else httpx.Response(200, json=FIXTURE)

    listings = make_provider(handler).search("Rolex", "126610LN")
    assert len(listings) == 7
    assert all(isinstance(price, float) for _, price in listings)


def test_search_skips_converted_currency_prices():
    fixture = {
        "itemSummaries": [
            {
                "itemId": "v1|1|0",
                "title": "Rolex Submariner 126610LN",
                "price": {
                    "value": "13000.00",
                    "currency": "USD",
                    "convertedFromValue": "10000.00",
                    "convertedFromCurrency": "GBP",
                },
            },
        ]
    }

    def handler(request):
        return token_response() if str(request.url).startswith(TOKEN_URL) else httpx.Response(200, json=fixture)

    listings = make_provider(handler).search("Rolex", "126610LN")
    assert listings == []


def test_token_is_cached_until_expiry():
    token_calls = 0
    now = [0.0]

    def handler(request):
        nonlocal token_calls
        if str(request.url).startswith(TOKEN_URL):
            token_calls += 1
            return token_response(f"tok{token_calls}")
        return httpx.Response(200, json={"itemSummaries": []})

    provider = make_provider(handler, clock=lambda: now[0])
    provider.search("Rolex", "126610LN")
    provider.search("Rolex", "126610LN")
    assert token_calls == 1
    now[0] = 7200.0
    provider.search("Rolex", "126610LN")
    assert token_calls == 2


def test_search_error_raises():
    def handler(request):
        return token_response() if str(request.url).startswith(TOKEN_URL) else httpx.Response(500, text="boom")

    with pytest.raises(EbayError, match="500"):
        make_provider(handler).search("Rolex", "126610LN")


def test_token_error_raises():
    with pytest.raises(EbayError, match="401"):
        make_provider(lambda request: httpx.Response(401, text="bad creds")).search("Rolex", "126610LN")


def test_search_401_clears_cached_token_and_refetches():
    token_calls = 0
    search_calls = 0

    def handler(request):
        nonlocal token_calls, search_calls
        if str(request.url).startswith(TOKEN_URL):
            token_calls += 1
            return token_response(f"tok{token_calls}")
        search_calls += 1
        if search_calls == 1:
            return httpx.Response(401, text="expired")
        assert request.headers["Authorization"] == "Bearer tok2"
        return httpx.Response(200, json={"itemSummaries": []})

    provider = make_provider(handler)
    with pytest.raises(EbayError, match="401"):
        provider.search("Rolex", "126610LN")
    assert token_calls == 1

    provider.search("Rolex", "126610LN")
    assert token_calls == 2
```

- [ ] **Step 3: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_ebay.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.ebay'`

- [ ] **Step 4: Implement `server/watchbox/ebay.py`**

```python
"""eBay Browse API price provider (median asking price of current listings)."""
import base64
import time
from typing import Callable

import httpx

from .pricing import PriceResult, summarize_prices

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
WRISTWATCHES_CATEGORY = "31387"
SEARCH_FILTER = "buyingOptions:{FIXED_PRICE},price:[500..],priceCurrency:USD"


class EbayError(Exception):
    pass


class EbayBrowseProvider:
    source = "ebay"

    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15)
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def _get_token(self) -> str:
        if self._token and self._clock() < self._expires_at - 60:
            return self._token
        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        response = self._http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        if response.status_code != 200:
            raise EbayError(f"token request failed: {response.status_code} {response.text[:200]}")
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = self._clock() + body["expires_in"]
        return self._token

    def search(self, brand: str, reference: str) -> list[tuple[str, float]]:
        response = self._http.get(
            SEARCH_URL,
            params={
                "q": f"{brand} {reference}",
                "category_ids": WRISTWATCHES_CATEGORY,
                "filter": SEARCH_FILTER,
                "limit": "100",
            },
            headers={"Authorization": f"Bearer {self._get_token()}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        )
        if response.status_code != 200:
            if response.status_code == 401:
                self._token = None
            raise EbayError(f"search failed: {response.status_code} {response.text[:200]}")
        listings = []
        for item in response.json().get("itemSummaries", []):
            price = item.get("price", {})
            converted_from = price.get("convertedFromCurrency")
            if converted_from and converted_from != "USD":
                continue
            if price.get("currency") == "USD" and "value" in price:
                listings.append((item.get("title", ""), float(price["value"])))
        return listings

    def get_price(self, brand: str, reference: str) -> PriceResult | None:
        return summarize_prices(self.search(brand, reference), reference, self.source)
```

Note: a 401 from `search` clears the cached token (`self._token = None`) before raising, since a cached token can go stale between calls; EBAY_US already returns foreign listings converted to USD, so `convertedFromCurrency` values are skipped unless they equal `"USD"`.

- [ ] **Step 5: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_ebay.py -q`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add server/watchbox/ebay.py server/tests/test_ebay.py server/tests/fixtures/ebay_search_126610ln.json
git commit -m "feat: eBay Browse API price provider"
```

---

### Task 6: Price refresh logic

**Files:**
- Create: `server/watchbox/refresh.py`
- Test: `server/tests/test_refresh.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_refresh.py`:
```python
from datetime import datetime, timezone

from watchbox import db
from watchbox.pricing import PriceResult
from watchbox.refresh import needs_refresh, refresh_all


def test_needs_refresh():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert needs_refresh(None, 6, now)
    assert needs_refresh("2026-09-27T05:59:00+00:00", 6, now)
    assert not needs_refresh("2026-09-27T07:00:00+00:00", 6, now)


def test_refresh_all_stores_prices_and_survives_failures(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ok = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    broken = db.add_watch(conn, "Omega", "Speedmaster", "BROKEN", 2, None)
    thin = db.add_watch(conn, "Tudor", "Black Bay", "THIN", 3, None)

    class Provider:
        def get_price(self, brand, reference):
            if reference == "BROKEN":
                raise RuntimeError("eBay down")
            if reference == "THIN":
                return None
            return PriceResult(13400.0, 10, "fake")

    assert refresh_all(conn, Provider()) == 1
    prices = {w.id: w.price_usd for w in db.list_watches(conn)}
    assert prices == {ok: 13400.0, broken: None, thin: None}


def test_refresh_all_skips_watch_deleted_during_fetch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    watch_id = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)

    class Provider:
        def get_price(self, brand, reference):
            db.delete_watch(conn, watch_id)
            return PriceResult(13400.0, 10, "fake")

    assert refresh_all(conn, Provider()) == 0
    assert db.list_watches(conn) == []


def test_refresh_watch_skips_storing_when_reference_changed_during_fetch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    watch_id = db.add_watch(conn, "Rolex", "Submariner", "126610LN", 1, None)
    watch = db.get_watch(conn, watch_id)

    class Provider:
        def get_price(self, brand, reference):
            db.update_watch(conn, watch_id, "Rolex", "Submariner", "DIFFERENT", 1, None)
            return PriceResult(13400.0, 10, "fake")

    from watchbox.refresh import refresh_watch

    assert refresh_watch(conn, Provider(), watch) is False
    assert db.get_watch(conn, watch_id).price_usd is None
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_refresh.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.refresh'`

- [ ] **Step 3: Implement `server/watchbox/refresh.py`**

```python
"""Fetches prices for watches and stores them; failures never raise."""
import logging
import sqlite3
from datetime import datetime, timedelta

from . import db
from .pricing import PriceProvider

log = logging.getLogger("watchbox.refresh")


def refresh_watch(conn: sqlite3.Connection, provider: PriceProvider, watch: db.Watch) -> bool:
    try:
        result = provider.get_price(watch.brand, watch.reference)
    except Exception:
        log.exception("price fetch failed for %s %s", watch.brand, watch.reference)
        return False
    if result is None:
        log.warning("not enough listings for %s %s", watch.brand, watch.reference)
        return False
    current = db.get_watch(conn, watch.id)
    if current is None or (current.brand, current.reference) != (watch.brand, watch.reference):
        log.info("watch %s changed or was deleted during fetch; discarding result", watch.id)
        return False
    try:
        db.add_price(conn, watch.id, result)
    except sqlite3.Error:
        log.exception("failed to store price for %s %s", watch.brand, watch.reference)
        return False
    log.info("%s %s -> $%.0f (%d listings)", watch.brand, watch.reference, result.price_usd, result.sample_size)
    return True


def refresh_all(conn: sqlite3.Connection, provider: PriceProvider) -> int:
    return sum(refresh_watch(conn, provider, w) for w in db.list_watches(conn))


def needs_refresh(last_fetch_iso: str | None, refresh_hours: float, now: datetime) -> bool:
    if last_fetch_iso is None:
        return True
    return now - datetime.fromisoformat(last_fetch_iso) >= timedelta(hours=refresh_hours)
```

Note: after `get_price` returns, the watch is re-read from the database and the result is discarded (without raising) if the watch was deleted or its brand/reference changed while the fetch was in flight; `db.add_price` is also wrapped so a storage failure is logged and reported as a failed refresh rather than propagating.

- [ ] **Step 4: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_refresh.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/refresh.py server/tests/test_refresh.py
git commit -m "feat: price refresh with failure isolation"
```

---

### Task 7: Config + web app + display API

**Files:**
- Create: `server/watchbox/config.py`, `server/watchbox/app.py`, `server/watchbox/templates/base.html`, `server/watchbox/templates/index.html`, `server/watchbox/templates/edit.html`, `server/watchbox/templates/_form.html`
- Test: `server/tests/test_app.py`, `server/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`server/tests/test_app.py`:
```python
import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from watchbox.app import create_app, run_scheduled
from watchbox.config import Settings
from watchbox.pricing import PriceResult


class FakeProvider:
    def __init__(self, prices):
        self.prices = prices
        self.calls = []

    def get_price(self, brand, reference):
        self.calls.append(reference)
        price = self.prices.get(reference)
        return PriceResult(price, 10, "fake") if price is not None else None


@pytest.fixture
def provider():
    return FakeProvider({"126610LN": 13400.0, "310.30.42.50.01.001": 6150.0})


@pytest.fixture
def client(tmp_path, provider):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=6, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, provider, run_scheduler=False)) as c:
        yield c


def add(client, **form):
    data = {"brand": "Rolex", "model": "Submariner", "reference": "126610LN", "slot": "", "nickname": ""} | form
    return client.post("/watches", data=data, follow_redirects=False)


def test_display_when_empty(client):
    body = client.get("/api/display").json()
    assert body["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]
    assert "generated_at" in body


def test_adding_a_watch_prices_it_and_shows_it_on_the_display(client, provider):
    response = add(client, slot="1")
    assert response.status_code == 303
    assert provider.calls == ["126610LN"]
    assert client.get("/api/display").json()["screens"] == [
        {"line1": "TOTAL 1 watch", "line2": "$13,400"},
        {"line1": "1 Submariner", "line2": "$13,400"},
    ]


def test_index_lists_watches_and_total(client):
    add(client, slot="1")
    page = client.get("/").text
    assert "Submariner" in page
    assert "$13,400" in page


def test_duplicate_slot_shows_error(client):
    add(client, slot="1")
    response = add(client, brand="Omega", model="Speedmaster", reference="310.30.42.50.01.001", slot="1")
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    assert "Slot 1 is already taken" in client.get(response.headers["location"]).text


def test_invalid_slot_is_rejected(client):
    response = add(client, slot="9")
    assert "error=" in response.headers["location"]
    assert client.get("/api/display").json()["screens"][0]["line1"] == "No watches yet"


def test_edit_page_prefills_form(client):
    add(client, slot="1")
    page = client.get("/watches/1/edit").text
    assert 'value="126610LN"' in page


def test_edit_missing_watch_is_404(client):
    assert client.get("/watches/99/edit").status_code == 404


def test_edit_then_delete(client):
    add(client, slot="1")
    response = client.post(
        "/watches/1",
        data={"brand": "Rolex", "model": "Submariner", "reference": "126610LN", "slot": "4", "nickname": "Sub"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/api/display").json()["screens"][1]["line1"] == "4 Sub"
    client.post("/watches/1/delete", follow_redirects=False)
    assert client.get("/api/display").json()["screens"][0]["line1"] == "No watches yet"


def test_refresh_now_reprices_everything(client, provider):
    add(client, slot="1")
    provider.calls.clear()
    response = client.post("/refresh", follow_redirects=False)
    assert response.status_code == 303
    assert provider.calls == ["126610LN"]


def test_missing_provider_shows_banner(tmp_path):
    settings = Settings(ebay_client_id="", ebay_client_secret="", refresh_hours=6, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, None, run_scheduler=False)) as c:
        assert "eBay keys missing" in c.get("/").text
        assert c.post("/watches", data={"brand": "Rolex", "model": "Sub", "reference": "1", "slot": "", "nickname": ""},
                      follow_redirects=False).status_code == 303


def test_reference_without_letters_or_digits_is_rejected(client):
    response = add(client, reference="-")
    assert "error=" in response.headers["location"]
    assert response.headers["location"].startswith("/?error=")
    assert client.get("/api/display").json()["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]


def test_whitespace_only_brand_or_model_is_rejected(client):
    response = add(client, brand="   ")
    assert "error=" in response.headers["location"]
    assert client.get("/api/display").json()["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]

    response = add(client, model="\t\n")
    assert "error=" in response.headers["location"]
    assert client.get("/api/display").json()["screens"] == [{"line1": "No watches yet", "line2": "Add on the app"}]


def test_run_scheduled_logs_and_swallows_exceptions(caplog):
    def boom():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="watchbox.app"):
        asyncio.run(run_scheduled(boom))
    assert "scheduled refresh failed" in caplog.text


def test_run_scheduled_runs_a_working_job(tmp_path):
    calls = []
    asyncio.run(run_scheduled(lambda: calls.append(1)))
    assert calls == [1]


def test_lifespan_cancels_scheduler_task_cleanly(tmp_path, provider):
    settings = Settings(ebay_client_id="x", ebay_client_secret="x", refresh_hours=1000, db_path=str(tmp_path / "t.db"))
    with TestClient(create_app(settings, provider, run_scheduler=True)) as c:
        c.get("/api/display")
    # If the scheduler task wasn't cancelled and awaited cleanly, this would raise or hang.
```

- [ ] **Step 2: Run to verify failure**

Run: `server/.venv/bin/pytest server/tests/test_app.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'watchbox.app'`

- [ ] **Step 3: Implement `server/watchbox/config.py`**

```python
"""Settings loaded from server/.env (see .env.example)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    ebay_client_id: str
    ebay_client_secret: str
    refresh_hours: float
    db_path: str


def load_settings() -> Settings:
    load_dotenv()
    refresh_hours = max(float(os.getenv("REFRESH_HOURS", "6")), 0.25)
    db_path = os.getenv("DB_PATH", "watchbox.db")
    if not os.path.isabs(db_path):
        db_path = str(SERVER_DIR / db_path)
    return Settings(
        ebay_client_id=os.getenv("EBAY_CLIENT_ID", ""),
        ebay_client_secret=os.getenv("EBAY_CLIENT_SECRET", ""),
        refresh_hours=refresh_hours,
        db_path=db_path,
    )
```

`server/tests/test_config.py`:
```python
from pathlib import Path

from watchbox.config import SERVER_DIR, load_settings


def _clear(monkeypatch, **overrides):
    # load_dotenv() never overrides an already-set env var, so setting every
    # relevant var here means a real server/.env can't leak into the test.
    defaults = {"EBAY_CLIENT_ID": "", "EBAY_CLIENT_SECRET": "", "REFRESH_HOURS": "6", "DB_PATH": "watchbox.db"}
    for key, value in (defaults | overrides).items():
        monkeypatch.setenv(key, value)


def test_refresh_hours_is_clamped_to_a_quarter_hour_minimum(monkeypatch):
    _clear(monkeypatch, REFRESH_HOURS="0")
    assert load_settings().refresh_hours == 0.25


def test_refresh_hours_above_minimum_is_kept(monkeypatch):
    _clear(monkeypatch, REFRESH_HOURS="6")
    assert load_settings().refresh_hours == 6.0


def test_relative_db_path_is_resolved_against_the_server_directory(monkeypatch):
    _clear(monkeypatch, DB_PATH="watchbox.db")
    assert load_settings().db_path == str(SERVER_DIR / "watchbox.db")


def test_absolute_db_path_is_kept_as_is(monkeypatch, tmp_path):
    absolute = str(tmp_path / "somewhere" / "t.db")
    _clear(monkeypatch, DB_PATH=absolute)
    assert load_settings().db_path == absolute


def test_server_dir_is_the_server_directory():
    assert (SERVER_DIR / "watchbox").is_dir()
    assert Path(SERVER_DIR).name == "server"
```

- [ ] **Step 4: Implement `server/watchbox/app.py`**

```python
"""FastAPI app: watch management pages, the LCD display API, and the price scheduler."""
import asyncio
import contextlib
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import db, refresh
from .config import Settings
from .display import build_screens, format_price, time_ago
from .pricing import PriceProvider

log = logging.getLogger("watchbox.app")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
SLOTS = range(1, 9)
FormStr = Annotated[str, Form()]


def parse_slot(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if not raw.isdigit() or not 1 <= int(raw) <= 8:
        raise ValueError("Slot must be between 1 and 8")
    return int(raw)


def validate_reference(reference: str) -> None:
    if not re.sub(r"[^a-z0-9]", "", reference.lower()):
        raise ValueError("Reference number must contain letters or digits")


def validate_required(brand: str, model: str) -> None:
    if not brand.strip() or not model.strip():
        raise ValueError("Brand and model are required")


def redirect(path: str, error: str | None = None) -> RedirectResponse:
    url = f"{path}?error={quote(error)}" if error else path
    return RedirectResponse(url, status_code=303)


async def run_scheduled(fn) -> None:
    """Runs a scheduled job in a thread; any failure is logged, never raised, so the loop keeps going."""
    try:
        await asyncio.to_thread(fn)
    except Exception:
        log.exception("scheduled refresh failed")


def create_app(settings: Settings, provider: PriceProvider | None, run_scheduler: bool = True) -> FastAPI:
    def get_conn():
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[object, Depends(get_conn)]

    def refresh_one(watch_id: int) -> None:
        if provider is None:
            return
        conn = db.connect(settings.db_path)
        try:
            watch = db.get_watch(conn, watch_id)
            if watch:
                refresh.refresh_watch(conn, provider, watch)
        finally:
            conn.close()

    def refresh_everything() -> None:
        if provider is None:
            return
        conn = db.connect(settings.db_path)
        try:
            refresh.refresh_all(conn, provider)
        finally:
            conn.close()

    def check_and_refresh_if_stale() -> None:
        conn = db.connect(settings.db_path)
        try:
            stale = refresh.needs_refresh(db.latest_fetch_time(conn), settings.refresh_hours, datetime.now(timezone.utc))
        finally:
            conn.close()
        if stale:
            refresh_everything()

    async def scheduler() -> None:
        await run_scheduled(check_and_refresh_if_stale)
        while True:
            await asyncio.sleep(settings.refresh_hours * 3600)
            await run_scheduled(refresh_everything)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(scheduler()) if run_scheduler and provider else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="WatchBox v0", lifespan=lifespan)

    def render(request: Request, name: str, **context) -> HTMLResponse:
        context |= {"format_price": format_price, "time_ago": time_ago, "slots": SLOTS,
                    "has_provider": provider is not None}
        return templates.TemplateResponse(request, name, context)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, conn: Conn, error: str | None = None):
        watches = db.list_watches(conn)
        priced = [w for w in watches if w.price_usd is not None]
        return render(request, "index.html", watches=watches, total=sum(w.price_usd for w in priced),
                      priced_count=len(priced), error=error, fw=None, action="/watches", submit_label="Add watch")

    @app.post("/watches")
    def create_watch(background: BackgroundTasks, conn: Conn, brand: FormStr, model: FormStr, reference: FormStr,
                     slot: FormStr = "", nickname: FormStr = ""):
        try:
            validate_required(brand, model)
            validate_reference(reference)
            watch_id = db.add_watch(conn, brand.strip(), model.strip(), reference.strip(), parse_slot(slot),
                                    nickname.strip() or None)
        except (ValueError, db.SlotTakenError) as e:
            return redirect("/", str(e))
        background.add_task(refresh_one, watch_id)
        return redirect("/")

    @app.get("/watches/{watch_id}/edit", response_class=HTMLResponse)
    def edit_watch(request: Request, watch_id: int, conn: Conn, error: str | None = None):
        watch = db.get_watch(conn, watch_id)
        if watch is None:
            raise HTTPException(404, "Watch not found")
        return render(request, "edit.html", watch=watch, error=error, fw=watch,
                      action=f"/watches/{watch_id}", submit_label="Save")

    @app.post("/watches/{watch_id}")
    def update_watch(watch_id: int, background: BackgroundTasks, conn: Conn, brand: FormStr, model: FormStr,
                     reference: FormStr, slot: FormStr = "", nickname: FormStr = ""):
        if db.get_watch(conn, watch_id) is None:
            raise HTTPException(404, "Watch not found")
        try:
            validate_required(brand, model)
            validate_reference(reference)
            db.update_watch(conn, watch_id, brand.strip(), model.strip(), reference.strip(), parse_slot(slot),
                            nickname.strip() or None)
        except (ValueError, db.SlotTakenError) as e:
            return redirect(f"/watches/{watch_id}/edit", str(e))
        background.add_task(refresh_one, watch_id)
        return redirect("/")

    @app.post("/watches/{watch_id}/delete")
    def delete_watch(watch_id: int, conn: Conn):
        db.delete_watch(conn, watch_id)
        return redirect("/")

    @app.post("/refresh")
    def refresh_now(background: BackgroundTasks):
        background.add_task(refresh_everything)
        return redirect("/")

    @app.get("/api/display")
    def display(conn: Conn):
        return {"generated_at": db.now_iso(), "screens": build_screens(db.list_watches(conn))}

    return app
```

- [ ] **Step 5: Create the templates**

`server/watchbox/templates/base.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WatchBox</title>
  <style>
    :root { --bg: #f6f5f2; --card: #fff; --ink: #1b1b1b; --muted: #6b6b6b; --line: #e3e1dc; --accent: #1f5f4a; --warn: #fff4d6; --err: #fde2e1; }
    @media (prefers-color-scheme: dark) { :root { --bg: #121314; --card: #1c1d1f; --ink: #eee; --muted: #9a9a9a; --line: #2c2d30; --accent: #6fd3a8; --warn: #3a3217; --err: #3b1c1c; } }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.45 -apple-system, system-ui, sans-serif; }
    main { max-width: 640px; margin: 0 auto; padding: 20px 16px 48px; }
    h1 { font-size: 15px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin: 0; }
    h2 { font-size: 18px; margin: 32px 0 12px; }
    .total { font-size: 44px; font-weight: 650; margin: 4px 0 0; font-variant-numeric: tabular-nums; }
    .muted { color: var(--muted); font-size: 14px; }
    .banner { background: var(--warn); padding: 10px 12px; border-radius: 8px; font-size: 14px; }
    .banner.error { background: var(--err); }
    .watch { display: grid; grid-template-columns: 36px 1fr auto; gap: 4px 12px; align-items: center; background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 12px; margin: 8px 0; }
    .slot { font-weight: 700; font-size: 20px; text-align: center; color: var(--accent); }
    .info { display: flex; flex-direction: column; min-width: 0; }
    .info strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .price { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
    .price small { display: block; font-weight: 400; color: var(--muted); font-size: 12px; }
    .watch a { grid-column: 2 / 4; font-size: 14px; color: var(--accent); }
    form.watch-form { display: grid; gap: 12px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px; }
    label { display: grid; gap: 4px; font-size: 14px; color: var(--muted); }
    input, select { font: inherit; color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
    button { font: inherit; font-weight: 600; border: 0; border-radius: 8px; padding: 12px 16px; background: var(--accent); color: var(--bg); cursor: pointer; }
    button.secondary { background: transparent; color: var(--accent); border: 1px solid var(--accent); }
    button.danger { background: transparent; color: #c0392b; border: 1px solid #c0392b; }
    .row { display: flex; gap: 8px; margin-top: 12px; }
  </style>
</head>
<body>
<main>
  {% if not has_provider %}<p class="banner">eBay keys missing: add them to server/.env and restart. Prices won't update.</p>{% endif %}
  {% if error %}<p class="banner error">{{ error }}</p>{% endif %}
  {% block content %}{% endblock %}
</main>
</body>
</html>
```

`server/watchbox/templates/_form.html`:
```html
<form method="post" action="{{ action }}" class="watch-form">
  <label>Brand <input name="brand" required value="{{ fw.brand if fw else '' }}" placeholder="Rolex"></label>
  <label>Model <input name="model" required value="{{ fw.model if fw else '' }}" placeholder="Submariner Date"></label>
  <label>Reference number <input name="reference" required value="{{ fw.reference if fw else '' }}" placeholder="126610LN"></label>
  <label>Slot
    <select name="slot">
      <option value="">No slot</option>
      {% for s in slots %}<option value="{{ s }}" {% if fw and fw.slot == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
  </label>
  <label>Nickname (optional) <input name="nickname" value="{{ (fw.nickname or '') if fw else '' }}" placeholder="Dad's Sub"></label>
  <button type="submit">{{ submit_label }}</button>
</form>
```

`server/watchbox/templates/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>WatchBox</h1>
<p class="total">{{ format_price(total) }}</p>
<p class="muted">{{ priced_count }} priced · median eBay asking price</p>

<section>
  {% for w in watches %}
  <article class="watch">
    <div class="slot">{{ w.slot if w.slot is not none else "–" }}</div>
    <div class="info">
      <strong>{{ w.nickname or w.model }}</strong>
      <span class="muted">{{ w.brand }} {{ w.reference }}</span>
    </div>
    <div class="price">
      {% if w.price_usd is not none %}
        {{ format_price(w.price_usd) }}<small>{{ w.sample_size }} listings · {{ time_ago(w.fetched_at) }}</small>
      {% else %}
        <span class="muted">no price yet</span>
      {% endif %}
    </div>
    <a href="/watches/{{ w.id }}/edit">Edit</a>
  </article>
  {% else %}
  <p class="muted">No watches yet. Add your first one below.</p>
  {% endfor %}
</section>

<form method="post" action="/refresh" class="row"><button class="secondary">Refresh prices now</button></form>

<h2>Add a watch</h2>
{% include "_form.html" %}
{% endblock %}
```

`server/watchbox/templates/edit.html`:
```html
{% extends "base.html" %}
{% block content %}
<p><a href="/">← Back</a></p>
<h2>Edit {{ watch.nickname or watch.model }}</h2>
{% include "_form.html" %}
<form method="post" action="/watches/{{ watch.id }}/delete" class="row" onsubmit="return confirm('Delete this watch?')">
  <button class="danger">Delete watch</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Run to verify pass**

Run: `server/.venv/bin/pytest server/tests/test_app.py server/tests/test_config.py -q`
Expected: `20 passed`

- [ ] **Step 7: Run the whole suite**

Run: `server/.venv/bin/pytest server/tests -q`
Expected: `57 passed`

- [ ] **Step 8: Commit**

```bash
git add server/watchbox/config.py server/watchbox/app.py server/watchbox/templates server/tests/test_app.py server/tests/test_config.py
git commit -m "feat: web app for watches and LCD display API"
```

---

### Task 8: Entry point, env template, eBay check script

**Files:**
- Create: `server/watchbox/__main__.py`, `server/.env.example`, `server/scripts/check_price.py`

- [ ] **Step 1: Create `server/.env.example`**

```text
# Copy to server/.env and fill in. Get keys at https://developer.ebay.com (Production keyset).
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=
REFRESH_HOURS=6
PORT=8000
DB_PATH=watchbox.db
```

- [ ] **Step 2: Create `server/watchbox/__main__.py`**

```python
"""Run with: cd server && .venv/bin/python -m watchbox"""
import logging
import os
import socket

import uvicorn

from .app import create_app
from .config import load_settings
from .ebay import EbayBrowseProvider


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = load_settings()
    provider = None
    if settings.ebay_client_id and settings.ebay_client_secret:
        provider = EbayBrowseProvider(settings.ebay_client_id, settings.ebay_client_secret)
    else:
        logging.warning("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set; prices will not update")
    port = int(os.getenv("PORT", "8000"))
    logging.info("Web app:              http://localhost:%d", port)
    logging.info("ESP32 SERVER_URL:     http://%s:%d", lan_ip(), port)
    uvicorn.run(create_app(settings, provider), host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create `server/scripts/check_price.py`**

```python
"""Manual sanity check: python scripts/check_price.py Rolex 126610LN  (run from server/)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watchbox.config import load_settings  # noqa: E402
from watchbox.ebay import EbayBrowseProvider  # noqa: E402
from watchbox.pricing import listing_matches, summarize_prices  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/check_price.py <brand> <reference>")
    brand, reference = sys.argv[1], sys.argv[2]
    settings = load_settings()
    if not (settings.ebay_client_id and settings.ebay_client_secret):
        sys.exit("Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET in server/.env first")
    listings = EbayBrowseProvider(settings.ebay_client_id, settings.ebay_client_secret).search(brand, reference)
    kept = sum(listing_matches(title, reference) for title, _ in listings)
    print(f"{len(listings)} USD listings, {kept} match {reference} and aren't accessories (✓)\n")
    for title, price in sorted(listings, key=lambda item: item[1]):
        flag = "✓" if listing_matches(title, reference) else " "
        print(f" {flag} ${price:>10,.0f}  {title[:80]}")
    result = summarize_prices(listings, reference, "ebay")
    print("\nPrice:", f"${result.price_usd:,.0f} (median of {result.sample_size} after outliers)" if result else "not enough data")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke-test the server without keys**

Run (background): `cd server && .venv/bin/python -m watchbox`
Then: `curl -s localhost:8000/api/display`
Expected: `{"generated_at":"…","screens":[{"line1":"No watches yet","line2":"Add on the app"}]}`. The log prints a warning about missing eBay keys and an `ESP32 SERVER_URL: http://192.168.x.x:8000` line. Stop the server.

- [ ] **Step 5: Commit**

```bash
git add server/watchbox/__main__.py server/.env.example server/scripts/check_price.py
git commit -m "feat: server entry point and eBay check script"
```

---

### Task 9: [USER] eBay keys + live price check

- [ ] **Step 1: [USER] Create eBay developer keys**
  1. Sign up at https://developer.ebay.com, verify your email, and wait for approval (usually minutes, sometimes a day).
  2. Go to **Application Keys** and create a **Production** keyset.
  3. eBay asks about **Marketplace Account Deletion** notifications. Choose the **exempt/opt-out** option, since this app stores no eBay user data.
  4. `cp server/.env.example server/.env`, then paste the **App ID (Client ID)** and **Cert ID (Client Secret)**.

- [ ] **Step 2: Live check**

Run: `cd server && .venv/bin/python scripts/check_price.py Rolex 126610LN`
Expected: a list of listings with ✓ marks and `Price: $1x,xxx (median of N after outliers)`. If most ✓ rows look wrong (accessories slipping through), add phrases to `JUNK_PHRASES` in `server/watchbox/pricing.py` with a test in `test_pricing.py`.

- [ ] **Step 3: Run the app with real prices**

Run: `cd server && .venv/bin/python -m watchbox`, open http://localhost:8000, and add 2–3 of your watches.
Expected: each shows a price within a few seconds. Note the `ESP32 SERVER_URL` from the log for Task 11.

macOS may ask "Allow Python to accept incoming network connections?" Click **Allow**, or the ESP32 can't reach the app.

---

### Task 10: Firmware toolchain + I2C scan

**Files:**
- Create: `firmware/i2c_scan/i2c_scan.ino`

- [ ] **Step 1: Install arduino-cli and the ESP32 core**

Run:
```bash
brew install arduino-cli
arduino-cli config init --overwrite
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install "LiquidCrystal I2C" ArduinoJson
```
Expected: ends with `Platform esp32:esp32@3.x.x installed` and both libraries installed. If `brew` is missing, install Homebrew from https://brew.sh first.

- [ ] **Step 2: Create `firmware/i2c_scan/i2c_scan.ino`**

```cpp
// Prints the address of every I2C device (the LCD backpack is usually 0x27 or 0x3F).
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin();  // ESP32 defaults: SDA = GPIO21, SCL = GPIO22
}

void loop() {
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("I2C device at 0x%02X\n", addr);
      found++;
    }
  }
  if (found == 0) Serial.println("No I2C devices found - check SDA/SCL wiring");
  Serial.println("---");
  delay(3000);
}
```

- [ ] **Step 3: Compile**

Run: `arduino-cli compile --fqbn esp32:esp32:esp32 firmware/i2c_scan`
Expected: `Sketch uses … bytes` with no errors.

- [ ] **Step 4: Commit**

```bash
git add firmware/i2c_scan
git commit -m "feat: I2C scan sketch for LCD bring-up"
```

- [ ] **Step 5: [USER] Wire the LCD and flash the scan**

Wiring (ESP32 unplugged):

| LCD backpack | ESP32 pin |
|---|---|
| GND | GND |
| VCC | 5V (labelled VIN or 5V) |
| SDA | GPIO21 |
| SCL | GPIO22 |

Plug in USB, then run `arduino-cli board list` to find the port (for example `/dev/cu.usbserial-0001` or `/dev/cu.wchusbserial…`), and:
```bash
arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 firmware/i2c_scan
arduino-cli monitor -p /dev/cu.usbserial-0001 -c baudrate=115200
```
Expected: `I2C device at 0x27` (or `0x3F`). Write it down for Task 11. If the upload hangs at `Connecting....`, hold the board's **BOOT** button until it starts writing.

---

### Task 11: WatchBox firmware

**Files:**
- Create: `firmware/watchbox_v0/watchbox_v0.ino`, `firmware/watchbox_v0/config.example.h`
- Create (gitignored): `firmware/watchbox_v0/config.h`

- [ ] **Step 1: Create `firmware/watchbox_v0/config.example.h`**

```cpp
#pragma once
// Copy to config.h (gitignored) and fill in.
#define WIFI_SSID  "your-wifi-name"              // 2.4 GHz network; the ESP32 can't join 5 GHz
#define WIFI_PASS  "your-wifi-password"
#define SERVER_URL "http://192.168.1.50:8000"    // "ESP32 SERVER_URL" printed by the server at startup
#define LCD_ADDR   0x27                          // from the i2c_scan sketch (0x27 or 0x3F)
```

- [ ] **Step 2: Create `firmware/watchbox_v0/watchbox_v0.ino`**

```cpp
// WatchBox v0: shows the collection value from the Mac app on a 16x2 I2C LCD.
// The server does all formatting; this sketch fetches /api/display and cycles screens.
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "config.h"

const unsigned long FETCH_INTERVAL_MS = 60000;
const unsigned long SCREEN_INTERVAL_MS = 4000;
const unsigned long DEBOUNCE_MS = 300;
const int BUTTON_PIN = 4;  // optional push button to GND: next screen + refetch
const int MAX_SCREENS = 16;

struct Screen {
  char line1[17];
  char line2[17];
};

LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);
Screen screens[MAX_SCREENS];
int screenCount = 0;
int nextScreen = 0;
unsigned long screensShown = 0;
bool lastFetchOk = false;
bool haveFetched = false;
unsigned long lastFetchAt = 0;
unsigned long lastScreenAt = 0;
unsigned long lastButtonAt = 0;

// Pads to 16 chars instead of lcd.clear() so the screen doesn't flicker.
void show(const char* line1, const char* line2) {
  char buf[17];
  snprintf(buf, sizeof(buf), "%-16s", line1);
  lcd.setCursor(0, 0);
  lcd.print(buf);
  snprintf(buf, sizeof(buf), "%-16s", line2);
  lcd.setCursor(0, 1);
  lcd.print(buf);
}

bool fetchDisplay() {
  HTTPClient http;
  http.setTimeout(5000);
  if (!http.begin(String(SERVER_URL) + "/api/display")) return false;
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    Serial.printf("GET /api/display failed: %d\n", code);
    http.end();
    return false;
  }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getStream());
  http.end();
  if (err) {
    Serial.printf("JSON error: %s\n", err.c_str());
    return false;
  }
  int count = 0;
  for (JsonObject s : doc["screens"].as<JsonArray>()) {
    if (count >= MAX_SCREENS) break;
    strlcpy(screens[count].line1, s["line1"] | "", sizeof(screens[count].line1));
    strlcpy(screens[count].line2, s["line2"] | "", sizeof(screens[count].line2));
    count++;
  }
  screenCount = count;
  if (nextScreen >= screenCount) nextScreen = 0;
  Serial.printf("Fetched %d screens\n", screenCount);
  return true;
}

void showNextScreen() {
  screensShown++;
  // Offline: keep showing the last good data, but every 3rd screen says so.
  if (!lastFetchOk && (screenCount == 0 || screensShown % 3 == 0)) {
    show("Server offline", "retrying...");
    return;
  }
  if (screenCount == 0) {
    show("No data", "");
    return;
  }
  show(screens[nextScreen].line1, screens[nextScreen].line2);
  nextScreen = (nextScreen + 1) % screenCount;
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  lcd.init();
  lcd.backlight();
  show("WatchBox v0", "WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(250);
  Serial.print("WiFi connected, IP ");
  Serial.println(WiFi.localIP());
  show("WatchBox v0", "Loading...");
}

void loop() {
  unsigned long now = millis();
  bool pressed = digitalRead(BUTTON_PIN) == LOW && now - lastButtonAt > DEBOUNCE_MS;
  if (pressed) lastButtonAt = now;

  if (WiFi.status() != WL_CONNECTED) {
    show("WatchBox v0", "WiFi...");
    delay(500);
    return;
  }

  if (!haveFetched || pressed || now - lastFetchAt >= FETCH_INTERVAL_MS) {
    lastFetchOk = fetchDisplay();
    lastFetchAt = now;
    haveFetched = true;
  }

  if (pressed || screensShown == 0 || now - lastScreenAt >= SCREEN_INTERVAL_MS) {
    lastScreenAt = now;
    showNextScreen();
  }
  delay(20);
}
```

- [ ] **Step 3: Create a local config and compile**

Run:
```bash
cp firmware/watchbox_v0/config.example.h firmware/watchbox_v0/config.h
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/watchbox_v0
```
Expected: `Sketch uses … bytes` with no errors. Ignore the warning that LiquidCrystal I2C "may be incompatible" with esp32; it works.

- [ ] **Step 4: Verify config.h is ignored**

Run: `git status --short firmware/`
Expected: `config.h` is **not** listed (`.gitignore` has `firmware/**/config.h`).

- [ ] **Step 5: Commit**

```bash
git add firmware/watchbox_v0/watchbox_v0.ino firmware/watchbox_v0/config.example.h
git commit -m "feat: ESP32 LCD firmware for WatchBox v0"
```

- [ ] **Step 6: [USER] Configure, flash, and verify**
  1. Edit `firmware/watchbox_v0/config.h` with your 2.4 GHz Wi-Fi, the `ESP32 SERVER_URL` from the server log, and the LCD address from Task 10.
  2. With the server running (Task 9, Step 3):
     ```bash
     arduino-cli upload -p /dev/cu.usbserial-0001 --fqbn esp32:esp32:esp32 firmware/watchbox_v0
     arduino-cli monitor -p /dev/cu.usbserial-0001 -c baudrate=115200
     ```
  3. Expected: the LCD shows `WiFi...`, then `Loading...`, then cycles `TOTAL n watches` / `$…` and each watch every 4 s. The serial log shows `Fetched N screens` every 60 s.
  4. Stop the server. Within about 60 s, every 3rd screen shows `Server offline`. Restart the server and it recovers.
  5. Add a watch in the web app. It appears on the LCD within 60 s, or immediately if you press the optional button on GPIO4.
  6. If the LCD backlight is on but there's no text, turn the blue contrast potentiometer on the backpack.

---

### Task 12: Enclosure

**Files:**
- Create: `enclosure/watchbox_v0.scad`

- [ ] **Step 1: Install OpenSCAD**

Run: `brew install --cask openscad`
Expected: `openscad --version` prints a version. If `openscad` isn't on PATH, use `/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD` in the commands below.

- [ ] **Step 2: Create `enclosure/watchbox_v0.scad`**

```openscad
// WatchBox v0 enclosure: I2C LCD1602 on the front, ESP32 devkit on a rail on the back plate.
// Export:  openscad -D 'part="front"' -o front.stl watchbox_v0.scad   (part = "front" | "back" | "assembly")
// Units: mm. Front shell prints face-down; back plate prints flat, rail up. No supports.

part = "assembly";

// ---------- Measure your parts and edit these ----------
lcd_pcb        = [80, 36];         // LCD PCB width x height
lcd_hole_sp    = [75, 31];         // LCD mounting-hole spacing (centre to centre)
lcd_frame      = [71.3, 24.3, 7];  // display frame w x h, and how far it stands off the PCB front
lcd_back_depth = 14;               // PCB back to top of the I2C backpack (incl. pins)
esp_board      = [55, 28];         // ESP32 board length x width (measure yours!)
esp_raise      = 18;               // rail height: room for header pins + Dupont connectors
esp_top        = 4;                // tallest part on top of the ESP32 (module / USB socket)
usb_cut        = [13, 9];          // cable plug clearance (width x height)
screw_pilot    = 2.6;              // pilot hole for M3 self-tapping (2.2 for M2.5)
screw_clear    = 3.4;              // clearance hole in the back plate
wall           = 2;
clr            = 0.3;
gap            = 4;                // air gap between LCD stack and ESP32 stack
button_hole    = true;             // hole in the top wall for the optional GPIO4 button
button_d       = 7;
// --------------------------------------------------------

$fn = 32;
boss_d = 7;
in_w = lcd_pcb.x + 2 * clr + 14;
in_h = lcd_pcb.y + 2 * clr + 14;
lcd_post_h = lcd_frame.z - wall;                         // frame face ends flush with the front
lcd_stack = lcd_post_h + 1.6 + lcd_back_depth;
esp_stack = esp_raise + 1.6 + esp_top;
in_d = lcd_stack + gap + esp_stack;
out = [in_w + 2 * wall, in_h + 2 * wall, in_d + wall];  // front shell, open at the back
cx = out.x / 2;
cy = out.y / 2;

// ESP32 footprint (shared by shell USB notch and back-plate rail): USB end near the right wall.
esp_x1 = wall + in_w - 1;
esp_x0 = esp_x1 - esp_board.x;
usb_z = out.z - esp_raise - 1.6 - esp_top / 2;          // USB socket centre, measured from front face

boss_pos = [for (x = [wall + boss_d / 2, out.x - wall - boss_d / 2],
                 y = [wall + boss_d / 2, out.y - wall - boss_d / 2]) [x, y]];
lcd_holes = [for (sx = [-1, 1], sy = [-1, 1]) [cx + sx * lcd_hole_sp.x / 2, cy + sy * lcd_hole_sp.y / 2]];

module rounded_box(size, r = 3) {
  hull() for (x = [r, size.x - r], y = [r, size.y - r]) translate([x, y, 0]) cylinder(r = r, h = size.z);
}

module front_shell() {
  difference() {
    union() {
      difference() {
        rounded_box(out);
        translate([wall, wall, wall]) cube([in_w, in_h, in_d + 1]);
      }
      for (p = lcd_holes) translate([p.x, p.y, wall]) cylinder(d = 5.5, h = lcd_post_h);
      for (p = boss_pos) translate([p.x, p.y, wall]) cylinder(d = boss_d, h = in_d);
    }
    // display window (the LCD frame sits in it, flush with the face)
    translate([cx - lcd_frame.x / 2 - clr, cy - lcd_frame.y / 2 - clr, -1])
      cube([lcd_frame.x + 2 * clr, lcd_frame.y + 2 * clr, wall + 2]);
    // LCD post pilot holes (blind: they don't pierce the front face)
    for (p = lcd_holes) translate([p.x, p.y, wall + 0.6]) cylinder(d = screw_pilot, h = lcd_post_h);
    // back-plate screw pilots
    for (p = boss_pos) translate([p.x, p.y, out.z - 12]) cylinder(d = screw_pilot, h = 13);
    // USB notch in the right wall, open to the back edge
    translate([out.x - wall - 1, cy - usb_cut.x / 2, usb_z - usb_cut.y / 2])
      cube([wall + 2, usb_cut.x, out.z]);
    // optional button hole in the top wall, behind the LCD stack
    if (button_hole)
      translate([cx - 25, out.y - wall - 1, wall + lcd_stack + 6])
        rotate([-90, 0, 0]) cylinder(d = button_d, h = wall + 2);
  }
}

module back_plate() {
  difference() {
    union() {
      rounded_box([out.x, out.y, wall]);
      // ESP32 rail between the pin rows; stick the board on with foam tape
      translate([esp_x0 + 4, cy - 7, wall]) cube([esp_board.x - 8, 14, esp_raise]);
      // stop at the antenna end so the board can't slide left (the right wall stops it the other way)
      translate([esp_x0 - 2, cy - 7, wall]) cube([2, 14, esp_raise + 3]);
    }
    for (p = boss_pos) translate([p.x, p.y, -1]) cylinder(d = screw_clear, h = wall + 2);
    // vent slots above the board
    for (i = [0 : 4]) translate([cx - 30 + i * 13, cy + esp_board.y / 2 + 3, -1]) cube([6, 8, wall + 2]);
  }
}

if (part == "front") {
  front_shell();
} else if (part == "back") {
  back_plate();
} else {
  front_shell();
  color("gray") translate([0, 0, out.z + wall]) mirror([0, 0, 1]) back_plate();
}

echo(str("Outer size: ", out.x, " x ", out.y, " x ", out.z + wall, " mm"));
```

- [ ] **Step 3: Export STLs and a preview**

Run:
```bash
openscad -D 'part="front"' -o enclosure/watchbox_v0_front.stl enclosure/watchbox_v0.scad
openscad -D 'part="back"'  -o enclosure/watchbox_v0_back.stl  enclosure/watchbox_v0.scad
openscad -D 'part="assembly"' --imgsize=1200,900 --viewall --autocenter -o enclosure/preview.png enclosure/watchbox_v0.scad
```
Expected: both STLs are written with no `WARNING`/`ERROR` lines, and the console echoes `Outer size: 98.6 x 54.6 x 52.2 mm` (with default parameters). Open `enclosure/preview.png` and check the window is centred, the USB notch is on the right, and the rail is inside the box.

- [ ] **Step 4: Commit**

```bash
git add enclosure/watchbox_v0.scad enclosure/watchbox_v0_front.stl enclosure/watchbox_v0_back.stl enclosure/preview.png
git commit -m "feat: parametric enclosure for WatchBox v0"
```

- [ ] **Step 5: [USER] Measure, print, assemble**
  1. Measure the ESP32 board (length, width, and tallest part), the LCD frame and the backpack depth. Update the parameters at the top of the `.scad` and re-run Step 3.
  2. In Bambu Studio, import both STLs. Put the front shell **face-down** and the back plate **flat, rail up**. PLA, 0.2 mm layers, 3 walls, no supports.
  3. Screw the LCD to the 4 posts (M3 or M2.5 self-tapping), stick the ESP32 to the rail with foam tape with the USB end toward the right wall, connect the jumpers, and screw on the back plate with 4 M3 screws.

---

### Task 13: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

````markdown
# WatchBox v0

A prototype watch case that shows your collection's market value on a 16×2 LCD.
A local web app stores your watches and fetches eBay prices, and an ESP32 displays them.

## Run the app
```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # add your eBay Production keys
.venv/bin/python -m watchbox
```
Open http://localhost:8000 and add watches. The log prints the `ESP32 SERVER_URL` to put in the firmware config.

Check one price by hand: `.venv/bin/python scripts/check_price.py Rolex 126610LN`
Tests: `.venv/bin/pytest -q`

## Flash the ESP32
Wiring: LCD GND→GND, VCC→5V, SDA→GPIO21, SCL→GPIO22. Optional button: GPIO4→GND.
```bash
cp firmware/watchbox_v0/config.example.h firmware/watchbox_v0/config.h   # edit Wi-Fi, SERVER_URL, LCD_ADDR
arduino-cli board list
arduino-cli upload -p <port> --fqbn esp32:esp32:esp32 firmware/watchbox_v0
```
Don't know the LCD address? Flash `firmware/i2c_scan` first and watch the serial monitor.

## Print the enclosure
Edit the measurements at the top of `enclosure/watchbox_v0.scad`, then:
```bash
openscad -D 'part="front"' -o enclosure/watchbox_v0_front.stl enclosure/watchbox_v0.scad
openscad -D 'part="back"'  -o enclosure/watchbox_v0_back.stl  enclosure/watchbox_v0.scad
```
Front face-down, back plate flat, no supports.

## Notes
Prices are the median **asking** price of current eBay listings for the reference number, not sold prices.
The price source is swappable (`server/watchbox/pricing.py` → `PriceProvider`).
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README for WatchBox v0"
```

---

## Self-review notes

- **Spec coverage:**
  - Data model: Task 3. Provider interface and eBay filtering: Tasks 2 and 5. Scheduler and immediate pricing: Tasks 6 and 7.
  - Display endpoint and all formatting rules: Tasks 4 and 7. Web UI: Task 7. Config and .env: Tasks 7 and 8.
  - Firmware behaviors (boot, 60 s fetch, 4 s cycle, offline every 3rd screen, Wi-Fi reconnect, button): Task 11. I2C scan: Task 10.
  - Enclosure: Task 12. Manual eBay check: Tasks 8 and 9. End-to-end: Task 11, Step 6.
- **Test count:** pricing 9 + db 8 + display 9 + ebay 7 + refresh 4 + app 10 = 47.
- **Names used across tasks:** `PriceResult`, `get_price(brand, reference)`, `listing_matches`, `filter_listings`, `summarize_prices`, `Watch`, `SlotTakenError`, `db.now_iso`, `build_screens`, `format_price`, `time_ago`, `create_app(settings, provider, run_scheduler)`, `Settings(ebay_client_id, ebay_client_secret, refresh_hours, db_path)`.
