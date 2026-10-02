# WatchBox v1, Part 3: 3.5" Display Firmware: Design

**Date:** 2026-10-02
**Status:** Approved in brainstorming, awaiting spec review
**Builds on:** `2026-10-02-valuation-engine-design.md` (part 1), the server in `server/`, and the bring-up sketch `firmware/board_test_35/`.

## Context

The box's screen is an **ESP32-32E 3.5" board** (LCDwiki/Elecrow E32R35T):
- **Display:** ST7796 panel, 320×480, used in landscape at 480×320.
- **Touch:** XPT2046 resistive, sharing the HSPI bus (SCK 14, MOSI 13, MISO 12); LCD CS 15, DC 2, backlight 27; touch CS 33, touch interrupt 36.
- **Other hardware:** battery sense on ADC 34, and BOOT on IO0.
- **Mounting:** the board sits in the printed lid liner (`enclosure/lid_liner.scad`), behind its window.

Bring-up on 2026-10-02 established the following, which are now requirements:
- **SPI write clock 20 MHz.** At 40 MHz the colors came out garbled.
- **Normal colors:** inversion off, RGB order.
- **Touch calibration** `{378, 3815, 333, 301, 3689, 3781, 3687, 332}`, used with `setRotation(1)`.
- **The LovyanGFX library works.** The bring-up sketch used about 84% of the default 1.3 MB app partition.

## Decisions made in brainstorming

| Topic | Decision |
|---|---|
| Home screen | **A:** large gold total at the top, then a 4 × 2 slot map laid out like the insert |
| Detail screen | **A:** large estimate and confidence, then three figures: eBay sold, Chrono24 asking, accuracy |
| Setup | **A:** box hotspot + QR setup page now; account pairing comes with part 2 |
| Power | **A:** sleep after inactivity, wake on touch; no lid switch for now |
| Rendering | Draw directly with LovyanGFX (no LVGL, no server-rendered images) |

## Goals

1. Show the collection on the 3.5" screen as a slot map with per-watch detail screens, using the valuation engine's data.
2. Let a new owner set up Wi-Fi and the app address from a phone, with no reflashing.
3. Last for days on battery: deep sleep when not in use, and an instant display of cached data on wake.

## Non-goals

Account pairing and QR pairing to an account (part 2), slot presence sensors, a lid switch, price-trend charts, OTA updates, and controls on the box for editing watches.

## 1. Server: `GET /api/box`

The response contains structured data for the 3.5" box. `/api/display` stays unchanged for the 16×2 LCD box.

```json
{
  "generated_at": "2026-10-02T14:00:00+00:00",
  "total_usd": 39130,
  "priced": 4,
  "slots": [
    {"slot": 1, "watch": {
      "id": 1, "name": "Portugieser", "brand": "IWC", "model": "Portugieser Chronograph",
      "reference": "IW371615", "details": "Full set, Excellent",
      "estimate_usd": 6940, "estimated_reference": false, "confidence": "medium",
      "ebay": {"n": 0, "median": null, "p10": null, "p90": null},
      "chrono24": {"n": 37, "median": 6308},
      "accuracy": {"n": 0, "mdape": null},
      "as_of": "2026-10-02T09:14:00+00:00"}},
    {"slot": 5, "watch": null}
  ],
  "unslotted": []
}
```

- **`slots`** always has exactly 8 entries, ordered 1–8. An empty slot has `"watch": null`. Watches without a slot go in `unslotted`, using the same object shape.
- **`name`** is the nickname if set, otherwise the model, as plain text.
- **`details`** is "<box & papers label>, <condition label>", built with the existing `valuation.models.label()`.
- **`reference`** is the watch's own reference. `estimated_reference` is true when `price_reference` is set; the box then prefixes the price with "~".
- **Valuation fields** come from the latest valuation (`db.latest_valuations`). A watch with no valuation, but a v0 price (TheWatchAPI or eBay Browse), reports that price with `confidence: null` and empty eBay, Chrono24 and accuracy blocks. A watch with no price at all has `estimate_usd: null`.
- **`total_usd`** sums the estimates that are present, and **`priced`** counts them. All money values are whole-dollar integers, so the firmware doesn't format decimals.
- Implemented as a pure builder function `build_box_payload(watches, valuations)` in `server/watchbox/box.py`, plus a route in `app.py`.

## 2. Firmware layout: `firmware/watchbox_35/`

| File | Responsibility |
|---|---|
| `watchbox_35.ino` | Entry point, main loop, the screen state machine |
| `board.h` | LovyanGFX device class (pins, 20 MHz, colors, touch calibration) |
| `theme.h` | Colors, fonts, layout constants |
| `data.h/.cpp` | Box data model; fetching `/api/box`; parsing; caching in NVS |
| `screens.h/.cpp` | Drawing: status bar, home, detail, settings, setup, messages |
| `input.h/.cpp` | Touch handling: tap / swipe detection, hit-testing tiles and buttons |
| `power.h/.cpp` | Battery reading, backlight dimming, deep sleep and wake |
| `net.h/.cpp` | Wi-Fi with WiFiManager, the hotspot, settings stored in NVS |

- **Board settings:** `esp32:esp32:esp32` with **`PartitionScheme=huge_app`** (3 MB app, no OTA).
- **Libraries:** LovyanGFX, ArduinoJson 7, WiFiManager (tzapu).
- `config.h` is no longer used.

## 3. Screens (480 × 320, landscape)

**Theme**

| Element | Value |
|---|---|
| Background | #0B0C0E |
| Tile | #16191E |
| Text | #E9E9E9 |
| Muted text | #8B9099 |
| Gold (total, estimates) | #F2C46D |
| Confidence dots | high #5FD18B, medium #E7C160, low #E07A6A, no confidence grey |

Fonts are LovyanGFX FreeSans and FreeSansBold at 9/12/18/24 pt.

**Status bar** (24 px, every screen except setup)
- Left: the title or "‹ Back".
- Right: Wi-Fi indicator (●, or ○ when offline), battery ("82%" or "USB"), "updated h:mm", and a ⚙ icon (tap target 40×24).

**Home**
- **Total row:** the total in gold 24 pt at the left; "N watches · market estimate" muted on the right.
- **Slot map:** a 4 × 2 grid of tiles (about 110 × 100 px, 6 px gaps).
  - A tile with a watch shows the slot number (muted), its name (12 pt, up to 2 lines, ending in "…" if it doesn't fit), and the price (FreeSansBold 12 pt) with its confidence dot.
  - An empty slot is a dashed outline with "Empty".
  - A watch with no price shows "no price yet".
- **Tapping a watch tile** opens its detail screen; tapping an empty tile does nothing.
- **Unslotted watches** count toward the total but have no tile; the settings screen shows how many there are.

**Detail**
- **Status bar:** "‹ Back" on the left, "Slot N of 8" on the right.
- **Body:**
  - A muted line: BRAND · REFERENCE · details.
  - The name (18 pt).
  - The estimate (gold 24 pt bold, "~" prefix if estimated from another reference) plus the confidence dot and word.
  - Three columns:

    | Column | Main figure | Second line |
    |---|---|---|
    | eBay sold · 90 d | median | "N sales · $Xk–$Yk" (p10–p90) |
    | Chrono24 asking | median | "N listings" |
    | Accuracy | "±Z%" | "backtest, N sales" |

  - A column with no data shows "—" and "not enough data".
  - Footer (muted): "Updated <date time> · eBay + Chrono24".
- **Swiping left or right** moves to the next or previous slot that has a watch, wrapping around. Tapping Back, or **30 s with no touch**, returns home.

**Settings (⚙)**
- **Left:** a QR code, 150 px, encoding the app URL, with the label "Open the app on your phone".
- **Right:** Wi-Fi SSID and signal (dBm), app address, battery voltage and %, firmware version, and the count of unslotted watches if there are any.
- **Buttons:**
  - **Re-run setup:** asks for confirmation, then clears the Wi-Fi settings and restarts into setup.
  - **Back.**

**Setup** (no status bar)
- **Title:** "Set up your WatchBox".
- **Left:** a Wi-Fi QR code (`WIFI:T:nopass;S:WatchBox-XXXX;;`). XXXX is the last 4 hex digits of the MAC address.
- **Right:** the steps:
  1. Scan to join WatchBox-XXXX.
  2. The setup page opens. If it doesn't, go to 192.168.4.1.
  3. Choose your Wi-Fi, enter the app address, then save.

**Messages** (a banner under the status bar, or a full screen)
- **Offline:** "Can't reach the app — showing values from <time>". The cached data stays visible.
- **No data yet** (first boot after setup, app unreachable): "Waiting for the app at <url>…".
- **Low battery** (below 10%, on battery power): "Battery low — please charge".

## 4. Setup and network

- **WiFiManager handles the hotspot.**
  - The hotspot is open, named `WatchBox-XXXX`, with a captive portal.
  - The portal has a custom field "App address" (default `http://watchbox.local:8000`, placeholder `http://192.168.1.50:8000`).
  - The portal times out after 10 minutes, then the box restarts and tries again.
- **Storage:** the app address is saved in NVS (`Preferences` namespace `watchbox`, key `server`). WiFiManager stores the Wi-Fi credentials itself.
- **On boot:**
  - With no saved Wi-Fi, the box shows the setup screen and starts the portal. The setup screen is drawn from WiFiManager's AP-mode callback.
  - Otherwise it connects in the background, waiting up to 20 s. If that fails, it falls back to the cached data plus the offline banner, and keeps retrying every 30 s.
  - **Setup starts only on a first boot or "Re-run setup".** A temporary Wi-Fi outage must not drop a configured box into setup.
- **Fetching:** while awake, the box gets `GET <server>/api/box` on wake and then every 60 s.
  - It uses HTTP/1.0, a 3 s connect timeout and a 5 s read timeout.
  - It validates the payload: `slots` must be an array of 8.
  - It caches the raw JSON in NVS (`Preferences` key `box`, up to 6 KB) only after a successful parse.

## 5. Power

- **Dimming and sleep:** after **120 s** with no touch, the backlight dims to 15%. After **15 s more**, the box saves the current screen state and enters **deep sleep** with `esp_sleep_enable_ext0_wakeup(GPIO_NUM_36, 0)`; the XPT2046 interrupt goes low on touch. The backlight is off and Wi-Fi is stopped first.
- **On wake:**
  1. Draw home from the NVS cache in under 1 s.
  2. Connect Wi-Fi and fetch.
  3. Redraw when the new data differs.
  4. The touch that woke the box isn't treated as a tap.
- **Battery:**
  - The voltage is read as `analogReadMilliVolts(34) × 2`. This assumes the board's 1:2 divider; verify it against a multimeter during bring-up.
  - Conversion to %: linear from 3.30 V (0%) to 4.15 V (100%), clamped.
  - A reading under 2.5 V or over 4.5 V means "USB" (no battery fitted or charging artefacts).
  - Below 10% on battery shows the low-battery banner.
- **Plugged-in mode:** with no battery reading (USB), the sleep timer is **10 min** instead of 2 min.

## 6. Error handling

| Situation | Behaviour |
|---|---|
| App unreachable / HTTP error / bad JSON | Keep the cached data; offline banner with the cache time; retry next cycle |
| No cache and no app | "Waiting for the app at <url>…" |
| Wi-Fi lost while awake | ○ icon, auto-reconnect, offline banner after a failed fetch |
| Touch on an empty tile or outside targets | Ignored |
| Name too long for a tile | Wrapped to 2 lines, then "…" |
| NVS write fails | Logged to serial; the display is unaffected |

## 7. Testing

- **Server:** pytest tests for `build_box_payload` and `/api/box`:
  - always 8 slots;
  - empty slots;
  - unslotted watches;
  - a valuation-backed watch with all blocks;
  - a v0-price fallback;
  - no price at all;
  - the estimated-reference flag;
  - totals and integer rounding.
- **Firmware:** must compile with no warnings from our code. A small `formatPrice` / `truncate` helper set lives in a header with no hardware dependencies.
- **Hands-on acceptance on the owner's board:**
  1. Fresh setup through the hotspot from a phone.
  2. The home screen shows all 4 watches and empty slots 5–8.
  3. Tapping a tile opens its detail.
  4. Swiping moves between watches.
  5. The screen returns home after 30 s.
  6. Settings shows the QR code, and it opens the app.
  7. With the Mac app stopped, the offline banner shows with cached values.
  8. After 2 minutes the screen dims and the box sleeps; a touch wakes it with an instant cached display.
  9. "Re-run setup" works.

## Known limitations

- **Battery calibration:** the divider ratio is assumed and must be checked once.
- **Lid detection:** with no lid switch, the box sleeps on inactivity and not when the lid closes.
- **"watchbox.local" default:** the default app address assumes the Mac app is reachable by that name. Until mDNS is added to the server, the owner enters the Mac's IP address on the setup page.

## Implementation notes (2026-10-02)

These refinements came out of the implementation plan (`docs/superpowers/plans/2026-10-02-display-35.md`):

- **Time labels:** the payload adds `updated_label` (top level, the newest valuation time) and `as_of_label` (per watch). Both are local-time strings such as `"Oct 2, 1:14 PM"`, so the box needs no clock.
- **ASCII strings:** every string sent to the box is ASCII-folded (Glashütte → Glashutte), because the GFX fonts are ASCII-only.
- **Short `details` labels:** for example "Full set, Excellent".
- **ASCII stand-ins on screen:** "< Back" for "‹ Back", a three-line menu icon for ⚙, "+/-" for ±, and "-" for "·" and "—". The detail column labels are "eBay sold - 90 d", "Chrono24 asking" and "Accuracy".
- **Tile names** use 9 pt, so about 12 characters fit per line.
- **Waking from sleep always shows the home screen;** the screen state is not saved.
- **Offline banner** reads "Can't reach the app - values from <time>" so it fits the 480 px width.
- **Change detection:** the box ignores `generated_at` when deciding whether the data changed, so it only redraws and rewrites the NVS cache when the content differs.
