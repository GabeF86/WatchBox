# Watch Box Prototype v0: Design

**Date:** 2026-09-27
**Status:** Approved (brainstorming), awaiting spec review

## Context

The long-term product is a smart watch case: a 3D-printed heavy-duty case (about 250 × 205 mm) with an 8-slot insert (4 × 2 grid, slots about 55 × 85 mm, 42 mm deep). A 3.5" color screen inside the lid shows the live market value of the watches currently in the box. Each slot has a presence sensor, owners assign watches to numbered slots on a mobile-friendly website, and a watch's value counts only while its slot detects it. The box runs on a built-in LiPo with USB-C charging, pairs through a setup hotspot and a 6-digit code, and fetches ready-made screen data from a server. The server pulls prices from a licensed provider (WatchCharts) through a swappable price-provider layer.

**v0 is a much smaller first step** that proves the core loop with parts already on hand:
enter watches → fetch real market prices → show them on a screen in the box.

## Goals

1. Enter watches (brand, model, reference, slot 1–8, optional nickname) in a local web app.
2. Fetch a market price per watch from the eBay Browse API automatically.
3. Show the total and each watch's price on the kit's 16×2 I2C LCD, driven by the kit's ESP32.
4. House the ESP32 and LCD in a 3D-printed standalone enclosure (Bambu Studio).

## Non-goals (v0)

Slot presence sensors, battery power, the 3.5" color screen, user accounts or login, cloud hosting, pairing flow, lid-mounted panel, WatchCharts integration.

## Architecture

```
┌──────────────── Mac (same Wi-Fi) ────────────────┐        ┌──── ESP32 + LCD1602 ────┐
│  FastAPI app  ──  SQLite (watches, prices)       │        │  every 60 s:            │
│   ├─ web UI: add/edit/delete watches             │◄───────┤  GET /api/display       │
│   ├─ scheduler: refresh prices every 6 h         │  JSON  │  cycle lines every 4 s  │
│   └─ PriceProvider ── EbayBrowseProvider ──► eBay│        └─────────────────────────┘
└──────────────────────────────────────────────────┘
```

The box asks the server for ready-to-show data, and the server owns all logic and secrets. This matches the final product's architecture, so moving the server to the cloud later is a deployment change.

## Components

### 1. Server app (`server/`): Python 3.13, FastAPI, SQLite

**Data model**
- `watches`: id, brand, model, reference, slot (1–8, unique, nullable), nickname (nullable), created_at
- `prices`: id, watch_id, price_usd (numeric), sample_size (int), source (`"ebay"`), fetched_at. History is kept, and the latest row is the current price.

**Web UI** (server-rendered HTML, mobile-friendly, no JS framework)
- List of watches: slot, display name, current price, "fetched X ago", sample size.
- Add/edit form and delete button.
- "Refresh prices now" button.
- Collection total at the top.

**Price provider layer**
- Interface: `PriceProvider.get_price(brand, reference) -> PriceResult | None`, where `PriceResult` holds `price_usd`, `sample_size` and `source`.
- `EbayBrowseProvider`:
  - Authenticates with an OAuth client-credentials token (scope `https://api.ebay.com/oauth/api_scope`), cached until it expires.
  - Calls `GET /buy/browse/v1/item_summary/search` with `q="<brand> <reference>"`, `category_ids=31387` (Wristwatches), `filter=buyingOptions:{FIXED_PRICE},price:[500..],priceCurrency:USD`, `limit=100`.
  - Keeps only listings whose title contains the reference number, ignoring case, spaces and punctuation (so `126610 LN` matches `126610LN`).
  - Drops titles containing junk phrases (`box only`, `papers only`, `empty box`, `strap only`, `bracelet only`, `band only`, `links only`, `dial only`, `bezel only`, `bezel insert`, `crown only`, `case back`, `for parts`, `parts only`, `for repair`, `needs repair`, `repair only`, `homage`, `replica`, `instruction manual`, `manual only`, `booklet`). These are phrases, not single words, so normal titles like "Ceramic Bezel", "Oyster bracelet", or "Manual Wind" are kept.
  - Editing a watch's brand or reference clears its price history, so a stale price for the old reference is never shown.
  - Removes outliers outside [0.5 × median, 2 × median] of the remaining prices, then returns the median of what's left.
  - Returns `None` when fewer than 3 listings survive, and the UI shows "no price yet" (the server log records why).
- Only `USD` prices are used, and the value is the median **asking** price, labeled as such in the UI.

**Scheduler**
- Refreshes all watches on startup if the newest price is older than 6 h, then every 6 h (APScheduler or an asyncio loop).
- A new or edited watch is priced immediately.
- On eBay errors: log, keep the last good price, and retry at the next cycle.

**Display endpoint:** `GET /api/display`
```json
{
  "generated_at": "2026-09-27T14:00:00Z",
  "screens": [
    {"line1": "TOTAL 7 watches", "line2": "$84,250"},
    {"line1": "1 Submariner", "line2": "$13,400"},
    {"line1": "3 Nautilus 5711", "line2": "no price yet"}
  ]
}
```
- Every `line1` and `line2` is at most 16 ASCII characters, truncated server-side. Watches are ordered by slot, with unslotted watches last and no slot prefix.
- Display name: nickname if set, otherwise the model, prefixed with `"<slot> "`.
- Prices are formatted `$13,400`, whole dollars. `$1.2M` is used if the value exceeds 9 characters.
- An empty collection returns `screens: [{"line1": "No watches yet", "line2": "Add on the app"}]`.
- The total counts only watches that have a price. `line1` shows `TOTAL <n> watches`, where n is the number of priced watches.

**Config** (`server/.env`, gitignored): `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `REFRESH_HOURS=6`, `PORT=8000`. The app binds to `0.0.0.0` so the ESP32 can reach it on the LAN.

### 2. Firmware (`firmware/`): Arduino C++, built and flashed with arduino-cli

- Board: ESP32-WROOM-32E dev board (`esp32:esp32:esp32`).
- Libraries: `LiquidCrystal_I2C`, `ArduinoJson` (v7), `WiFi`, `HTTPClient`.
- Wiring: LCD VCC→5V (VIN), GND→GND, SDA→GPIO21, SCL→GPIO22. Optional push-button GPIO4→GND (internal pull-up), which skips to the next screen and forces an immediate re-fetch.
- `config.h` (gitignored, with `config.example.h` committed): `WIFI_SSID`, `WIFI_PASS`, `SERVER_URL` (for example `http://192.168.1.50:8000`), `LCD_ADDR` (default `0x27`).
- Behavior:
  - Boot: LCD shows `WatchBox v0` / `WiFi...` until connected.
  - Fetches `/api/display` on boot, then every 60 s.
  - Cycles through `screens`, one every 4 s.
  - If a fetch fails, it keeps showing the last good screens, and every 3rd screen is `Server offline` / `retrying...`. If it has never had data, it shows only that.
  - Reconnects to Wi-Fi automatically if dropped.
- A separate `firmware/i2c_scan/` sketch prints the LCD's I2C address to serial, for first-time bring-up.

### 3. Enclosure (`enclosure/`): OpenSCAD, exported to STL

- Two parts:
  - `front_shell`: front face with the LCD window, 4 LCD screw posts, 4 corner screw bosses, a USB notch open at the back edge, and an optional button hole in the top wall. It prints front-face-down.
  - `back_plate`: screw holes, vent slots, and a raised center rail (18 mm) that holds the ESP32 with foam tape. The rail sits between the two pin rows, so the Dupont jumpers stay attached underneath. It prints flat.
- Parametric: every part dimension is a variable at the top of `watchbox_v0.scad`. Defaults:
  - LCD1602 PCB 80 × 36 mm, mounting holes 75 × 31 mm (M3), visible area 64.5 × 16 mm, module depth with I2C backpack about 20 mm.
  - ESP32 board 55 × 28 mm (38-pin devkit). **Measure your board and update these values before printing.**
  - Wall 2 mm, clearance 0.3 mm.
- Prints flat without supports on the Bambu bed, in PLA or PETG. Closes with M3 screws, or M2.5 self-tapping into the bosses.
- OpenSCAD is installed with Homebrew (`brew install --cask openscad`). STLs are exported from the command line.

## Error handling summary

| Failure | Behavior |
|---|---|
| eBay auth or API error | Log it, keep the last price, retry next cycle. UI shows "fetched X ago". |
| Fewer than 3 usable listings | No new price stored. UI shows "no price yet" (same as never fetched; the server log records which), LCD shows `no price yet`. |
| Mac or server unreachable | LCD keeps the last data and shows a `Server offline` screen now and then. |
| Wi-Fi drops | Firmware reconnects and shows `WiFi...` while down. |
| Empty collection | `No watches yet` / `Add on the app`. |

## Testing

- **Server:** pytest suite using saved eBay JSON fixtures, with no live calls: junk filtering, outlier removal, median, the fewer-than-3 rule, 16-character formatting and truncation, price formatting (`$13,400`, `$1.2M`), `/api/display` ordering and empty state, and CRUD endpoints.
- **Manual eBay check:** a script prints the chosen price and the listings kept for one reference, to sanity-check the results.
- **Firmware:** the I2C scan sketch, then the full sketch pointed at the server. Check the offline behavior by stopping the server.
- **End to end:** add a watch in the UI and confirm it appears on the LCD within 60 s.

## User actions required

1. Create an eBay developer account, create a Production keyset, and choose the opt-out for marketplace account deletion notifications (the app stores no eBay user data). Put the keys in `server/.env`.
2. Measure the ESP32 board and update the enclosure parameters.
3. Wire 4 jumpers (plus an optional button), flash the board, and print 2 parts.

## Later (not v0)

Slot sensors (IR in the slot wall vs FSR under the pillow, tested in the insert), 3.5" ESP32-S3 display board, LiPo and charging, cloud deployment and accounts, pairing, WatchCharts provider, lid-mounted housing.
