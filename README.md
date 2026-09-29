# WatchBox v0

A prototype watch case that shows your collection's market value on a 16×2 LCD.
A local web app stores your watches and fetches market prices from TheWatchAPI (or eBay), and an ESP32 displays them.

## Hardware you need
- ESP32 devkit, I2C LCD1602 (PCF8574 backpack), USB cable and charger
- 4 female-female Dupont jumpers
- LCD: 4× M3 (or M2.5) self-tapping screws, **6 mm max** (longer ones can crack the front face)
- Back plate: 4× M3 × 10–12 mm self-tapping screws
- Double-sided foam tape for the ESP32

## Get a price source key
**TheWatchAPI (default):** register free at https://www.thewatchapi.com/register and put your API token in `server/.env` as `THEWATCHAPI_TOKEN`.
The free plan allows 25 requests a day, so keep `REFRESH_HOURS=24` (8 watches = 8 requests a day, plus one per watch you add or edit).
Their docs say price history may need the Standard plan; if so, the app logs a clear "may need a higher TheWatchAPI plan" error. Check with `scripts/check_price.py` right after you get your token.

**eBay (optional fallback):** if `THEWATCHAPI_TOKEN` is empty, the app uses eBay keys instead.
1. Sign up at https://developer.ebay.com and create a **Production** keyset.
2. When asked about Marketplace Account Deletion notifications, choose the opt-out/exempt option (this app stores no eBay user data).
3. Copy **App ID** → `EBAY_CLIENT_ID` and **Cert ID** → `EBAY_CLIENT_SECRET` in `server/.env`.

## Run the app
```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # add your THEWATCHAPI_TOKEN
.venv/bin/python -m watchbox
```
Open http://localhost:8000 and add watches. The log prints the `ESP32 SERVER_URL` to put in the firmware config.
On first run macOS asks whether Python may accept incoming network connections: click **Allow**, or the ESP32 can't reach the server.

Check one price by hand: `.venv/bin/python scripts/check_price.py Rolex 126610LN`
Tests: `.venv/bin/pytest -q`

## Flash the ESP32
Install arduino-cli (no Homebrew needed) and the ESP32 core once:
```bash
mkdir -p ~/.local/bin && curl -fsSL https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_macOS_ARM64.tar.gz | tar -xz -C ~/.local/bin arduino-cli
alias arduino-cli=~/.local/bin/arduino-cli      # or add ~/.local/bin to PATH
arduino-cli config init --overwrite
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index && arduino-cli core install esp32:esp32
arduino-cli lib install "LiquidCrystal I2C" ArduinoJson
```

Wiring: LCD GND→GND, VCC→5V (labelled VIN on some boards), SDA→GPIO21, SCL→GPIO22. Optional button: GPIO4→GND.
```bash
cp firmware/watchbox_v0/config.example.h firmware/watchbox_v0/config.h   # edit Wi-Fi (2.4 GHz), SERVER_URL, LCD_ADDR
arduino-cli board list                                                    # find the port, e.g. /dev/cu.usbserial-0001
arduino-cli compile --upload -p <port> --fqbn esp32:esp32:esp32 firmware/watchbox_v0
arduino-cli monitor -p <port> -c baudrate=115200
```
Don't know the LCD address? Flash `firmware/i2c_scan` first and watch the serial monitor.

Hardware notes:
- Backlight on but no text: turn the blue contrast potentiometer on the LCD backpack.
- A backpack powered from 5V pulls SDA/SCL up to 5V, but ESP32 pins are 3.3V. It usually works but is out of spec. For a long-running build, power the backpack from 3.3V (re-adjust the contrast pot) or use an I2C level shifter.
- If the LCD shows garbage or the board resets when Wi-Fi starts, the USB supply is too weak: use a better cable or charger.

## Print the enclosure
Download OpenSCAD from https://openscad.org/downloads.html (the macOS development snapshot works on Apple Silicon) and drag it to `/Applications` or `~/Applications`. Edit the measurements at the top of `enclosure/watchbox_v0.scad`, then:
```bash
alias openscad="$HOME/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"   # or /Applications/...
openscad -D 'part="front"' -o enclosure/watchbox_v0_front.stl enclosure/watchbox_v0.scad
openscad -D 'part="back"'  -o enclosure/watchbox_v0_back.stl  enclosure/watchbox_v0.scad
```
Front shell face-down, back plate flat with the rail up, no supports. In Bambu Studio, turn on elephant-foot compensation: the front face is the first layer and the window must stay full size.

Before mounting the LCD: the common PCF8574 backpack's 4 header pins stick out sideways past the LCD's short edge and won't fit in the box. Gently bend them 90° toward the back (or solder the wires on directly).
Stick the ESP32 to the rail with its USB end toward the right wall (the USB notch). When closing the box, the tall stop at the rail's other end must point away from the notch.

## Notes
Prices are **asking** prices, not sold prices. TheWatchAPI's data can lag (in Sept 2026 its newest point was 2024-07-17), so the page shows the data date. If your exact reference isn't listed, fill in "Price using reference" with a close variant; the price is then marked as an estimate (`~` on the LCD) and the LCD adds the month (e.g. `$12,413 Jul24`) when the data is over 30 days old: TheWatchAPI's latest indicative USD price for the reference number, or (eBay fallback) the median of current eBay listings.
The price source is swappable (`server/watchbox/pricing.py` → `PriceProvider`).
