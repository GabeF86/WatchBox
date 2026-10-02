#include "screens.h"

#include "board.h"
#include "format.h"
#include "theme.h"

using namespace theme;

namespace {
const char* FW_VERSION = "1.0.0";

uint16_t confidenceColor(const String& c) {
  if (c == "high") return CONF_HIGH;
  if (c == "medium") return CONF_MEDIUM;
  if (c == "low") return CONF_LOW;
  return NONE;
}

void text(const char* s, int x, int y, const lgfx::IFont* font, uint16_t color, uint8_t datum = top_left) {
  tft.setFont(font);
  tft.setTextColor(color);
  tft.setTextDatum(datum);
  tft.drawString(s, x, y);
}

void text(const String& s, int x, int y, const lgfx::IFont* font, uint16_t color, uint8_t datum = top_left) {
  text(s.c_str(), x, y, font, color, datum);
}

// Up to maxLines lines, breaking at spaces; the last line ends in "..." if the text doesn't fit.
void wrapText(const String& s, int x, int y, int maxW, int maxLines, const lgfx::IFont* font, uint16_t color) {
  tft.setFont(font);
  tft.setTextColor(color);
  tft.setTextDatum(top_left);
  int lineH = tft.fontHeight();
  String rest = s;
  for (int line = 0; line < maxLines && rest.length(); line++) {
    int fit = rest.length();
    while (fit > 1 && tft.textWidth(rest.substring(0, fit).c_str()) > maxW) fit--;
    if (fit < (int)rest.length() && line < maxLines - 1) {
      int space = rest.lastIndexOf(' ', fit);
      if (space > 0) fit = space;
    }
    String piece = rest.substring(0, fit);
    if (line == maxLines - 1 && fit < (int)rest.length()) {
      while (piece.length() && tft.textWidth((piece + "...").c_str()) > maxW) piece.remove(piece.length() - 1);
      piece += "...";
    }
    tft.drawString(piece.c_str(), x, y + line * lineH);
    rest = rest.substring(fit);
    rest.trim();
  }
}

// rightText replaces the Wi-Fi / battery / updated / menu indicators when given.
void statusBar(const char* left, const BoxStatus& s, const char* rightText = nullptr) {
  tft.fillRect(0, 0, W, BAR_H, BG);
  tft.drawFastHLine(0, BAR_H - 1, W, LINE);
  text(left, MARGIN, 5, &fonts::FreeSans9pt7b, MUTED);
  if (rightText) {
    text(rightText, W - MARGIN, 5, &fonts::FreeSans9pt7b, MUTED, top_right);
    return;
  }
  int x = W - MARGIN;
  for (int i = 0; i < 3; i++) tft.fillRect(x - 16, 7 + i * 5, 16, 2, MUTED);  // menu icon
  x -= 28;
  if (s.updated.length()) {
    text(s.updated, x, 5, &fonts::FreeSans9pt7b, MUTED, top_right);
    x -= tft.textWidth(s.updated.c_str()) + 12;
  }
  if (s.batteryPct >= 0) {  // battery outline with fill level
    tft.drawRect(x - 20, 7, 18, 10, MUTED);
    tft.fillRect(x - 2, 10, 2, 4, MUTED);
    int fill = (14 * s.batteryPct) / 100;
    tft.fillRect(x - 18, 9, fill, 6, s.lowBattery ? CONF_LOW : CONF_HIGH);
    x -= 26;
  }
  text(s.battery, x, 5, &fonts::FreeSans9pt7b, MUTED, top_right);
  x -= tft.textWidth(s.battery.c_str()) + 12;
  if (s.wifi) tft.fillCircle(x - 4, 12, 4, CONF_HIGH);
  else tft.drawCircle(x - 4, 12, 4, MUTED);
}

bool hasBanner(const BoxStatus& s) { return s.offline || s.lowBattery; }

void banner(const BoxStatus& s) {
  String msg;
  if (s.offline) msg = s.updated.length() ? "Can't reach the app - values from " + s.updated : "Can't reach the app";
  else if (s.lowBattery) msg = "Battery low - please charge";
  else return;
  tft.fillRect(0, BAR_H, W, 20, WARN_BG);
  text(msg, MARGIN, BAR_H + 3, &fonts::FreeSans9pt7b, GOLD);
}

void drawTile(const WatchInfo& w, const Area& r) {
  String num = String(w.slot);
  if (!w.present) {
    tft.fillRect(r.x, r.y, r.w, r.h, BG);
    tft.drawRoundRect(r.x, r.y, r.w, r.h, 8, LINE);
    text(num, r.x + 8, r.y + 6, &fonts::FreeSans9pt7b, NONE);
    text("Empty", r.x + 8, r.y + r.h / 2 - 8, &fonts::FreeSans9pt7b, NONE);
    return;
  }
  tft.fillRoundRect(r.x, r.y, r.w, r.h, 8, TILE);
  text(num, r.x + 8, r.y + 6, &fonts::FreeSans9pt7b, MUTED);
  tft.fillCircle(r.x + r.w - 12, r.y + 13, 4, confidenceColor(w.confidence));
  wrapText(w.name, r.x + 8, r.y + 30, r.w - 16, 2, &fonts::FreeSans9pt7b, TEXT);
  if (w.hasEstimate) {
    String price = String(w.estimatedRef ? "~" : "") + formatPrice(w.estimate);
    text(price, r.x + 8, r.y + r.h - 28, &fonts::FreeSansBold12pt7b, GOLD);
  } else {
    text("no price yet", r.x + 8, r.y + r.h - 24, &fonts::FreeSans9pt7b, MUTED);
  }
}

void column(int x, int y, const char* label, const String& value, const String& sub1, const String& sub2) {
  text(label, x, y, &fonts::FreeSans9pt7b, MUTED);
  text(value, x, y + 20, &fonts::FreeSansBold18pt7b, TEXT);
  text(sub1, x, y + 54, &fonts::FreeSans9pt7b, MUTED);
  if (sub2.length()) text(sub2, x, y + 72, &fonts::FreeSans9pt7b, MUTED);
}

void button(const Area& a, const char* label, uint16_t bg) {
  tft.fillRoundRect(a.x, a.y, a.w, a.h, 8, bg);
  text(label, a.x + a.w / 2, a.y + a.h / 2, &fonts::FreeSans9pt7b, TEXT, middle_center);
}
}  // namespace

Area screens::tileArea(int index) {
  int col = index % 4, row = index / 4;
  return {MARGIN + col * (TILE_W + GAP), GRID_TOP + row * (TILE_H + GAP), TILE_W, TILE_H};
}
Area screens::menuArea() { return {W - 56, 0, 56, BAR_H + 8}; }
Area screens::backArea() { return {0, 0, 110, BAR_H + 8}; }
Area screens::resetButtonArea() { return {190, 262, 170, 44}; }
Area screens::confirmNoArea() { return {90, 210, 130, 50}; }
Area screens::confirmYesArea() { return {260, 210, 130, 50}; }

void screens::homeStatusBar(const BoxStatus& s) { statusBar("WatchBox", s); }

void screens::home(const BoxData& d, const BoxStatus& s) {
  tft.fillScreen(BG);
  statusBar("WatchBox", s);
  banner(s);
  int ty = hasBanner(s) ? 48 : 32;
  text(formatPrice(d.total), MARGIN + 4, ty,
       hasBanner(s) ? &fonts::FreeSansBold18pt7b : &fonts::FreeSansBold24pt7b, GOLD);
  String caption = String(d.priced) + (d.priced == 1 ? " watch" : " watches") + " - market estimate";
  text(caption, W - MARGIN - 4, ty + 12, &fonts::FreeSans9pt7b, MUTED, top_right);
  for (int i = 0; i < 8; i++) drawTile(d.slots[i], tileArea(i));
}

void screens::detail(const BoxData& d, int index, const BoxStatus& s) {
  const WatchInfo& w = d.slots[index];
  tft.fillScreen(BG);
  String right = "Slot " + String(w.slot) + " of 8";
  statusBar("< Back", s, right.c_str());
  banner(s);
  int y = hasBanner(s) ? 50 : 32;
  text(w.brand + "  |  " + w.reference + "  |  " + w.details, MARGIN + 4, y, &fonts::FreeSans9pt7b, MUTED);
  text(w.name, MARGIN + 4, y + 20, &fonts::FreeSans18pt7b, TEXT);
  String est = w.hasEstimate ? String(w.estimatedRef ? "~" : "") + formatPrice(w.estimate) : String("no price yet");
  text(est, MARGIN + 4, y + 56, &fonts::FreeSansBold24pt7b, GOLD);
  int ex = MARGIN + 4 + tft.textWidth(est.c_str()) + 18;
  tft.fillCircle(ex, y + 76, 5, confidenceColor(w.confidence));
  text(w.confidence.length() ? w.confidence + " confidence" : String("no confidence data"), ex + 12, y + 68,
       &fonts::FreeSans9pt7b, TEXT);

  int cy = y + 116, cw = (W - 2 * MARGIN) / 3, cx = MARGIN + 4;
  if (w.hasEbay) {
    column(cx, cy, "eBay sold - 90 d", formatPrice(w.ebayMedian), String(w.ebayN) + " sales",
           formatK(w.ebayP10) + " - " + formatK(w.ebayP90));
  } else {
    column(cx, cy, "eBay sold - 90 d", "-", "not enough data", "");
  }
  if (w.hasC24) column(cx + cw, cy, "Chrono24 asking", formatPrice(w.c24Median), String(w.c24N) + " listings", "");
  else column(cx + cw, cy, "Chrono24 asking", "-", "not enough data", "");
  if (w.hasAcc) {
    char acc[16];
    snprintf(acc, sizeof acc, "+/-%.1f%%", w.mdape * 100);
    column(cx + 2 * cw, cy, "Accuracy", acc, "backtest, " + String(w.accN) + " sales", "");
  } else {
    column(cx + 2 * cw, cy, "Accuracy", "-", "not enough sales", "");
  }
  String footer = w.asOf.length() ? "Updated " + w.asOf + "  |  eBay + Chrono24" : String("eBay + Chrono24");
  text(footer, MARGIN + 4, H - 22, &fonts::FreeSans9pt7b, MUTED);
}

void screens::settings(const BoxStatus& s, const String& server, int unslotted, const String& ssid, int rssi,
                       int batteryMv) {
  tft.fillScreen(BG);
  statusBar("< Back", s, "Settings");
  tft.fillRect(MARGIN, 40, 164, 164, WHITE);
  tft.qrcode(server.c_str(), MARGIN + 7, 47, 150);
  text("Open the app", MARGIN + 82, 212, &fonts::FreeSans9pt7b, TEXT, top_center);
  text("on your phone", MARGIN + 82, 230, &fonts::FreeSans9pt7b, TEXT, top_center);

  int x = 190, y = 40;
  auto line = [&](const char* label, const String& value) {
    text(label, x, y, &fonts::FreeSans9pt7b, MUTED);
    text(value, x, y + 18, &fonts::FreeSans9pt7b, TEXT);
    y += 44;
  };
  line("Wi-Fi", ssid.length() ? ssid + " (" + String(rssi) + " dBm)" : String("not connected"));
  line("App address", server);
  line("Battery", s.batteryPct >= 0 ? String(batteryMv / 1000.0, 2) + " V (" + s.battery + ")" : String("USB power"));
  line("Firmware", FW_VERSION);
  if (unslotted > 0) line("Not in a slot", String(unslotted) + (unslotted == 1 ? " watch" : " watches"));
  button(resetButtonArea(), "Re-run setup", BUTTON);
}

void screens::confirmReset() {
  tft.fillScreen(BG);
  text("Re-run setup?", W / 2, 70, &fonts::FreeSansBold18pt7b, TEXT, top_center);
  text("This clears the saved Wi-Fi. The box restarts", W / 2, 120, &fonts::FreeSans9pt7b, MUTED, top_center);
  text("and shows the setup QR code.", W / 2, 140, &fonts::FreeSans9pt7b, MUTED, top_center);
  button(confirmNoArea(), "Cancel", BUTTON);
  button(confirmYesArea(), "Yes, reset", CONF_LOW);
}

void screens::setup(const String& apName) {
  tft.fillScreen(BG);
  text("Set up your WatchBox", MARGIN + 4, 14, &fonts::FreeSansBold18pt7b, TEXT);
  String wifiQr = "WIFI:T:nopass;S:" + apName + ";;";
  tft.fillRect(MARGIN, 60, 174, 174, WHITE);
  tft.qrcode(wifiQr.c_str(), MARGIN + 7, 67, 160);
  int x = 200, y = 70;
  const String lines[] = {"1. Scan to join " + apName, "2. The setup page opens.", "   If not, go to 192.168.4.1",
                          "3. Choose your Wi-Fi, enter the", "   app address, and save."};
  for (const String& l : lines) {
    text(l, x, y, &fonts::FreeSans9pt7b, TEXT);
    y += 26;
  }
  text("Waiting for setup...", x, y + 20, &fonts::FreeSans9pt7b, MUTED);
}

void screens::waiting(const String& server, const BoxStatus& s) {
  tft.fillScreen(BG);
  statusBar("WatchBox", s);
  text("Waiting for the app at", W / 2, 120, &fonts::FreeSans12pt7b, TEXT, top_center);
  text(server, W / 2, 152, &fonts::FreeSans12pt7b, GOLD, top_center);
  text("Check that the Mac app is running on the same Wi-Fi.", W / 2, 200, &fonts::FreeSans9pt7b, MUTED,
       top_center);
}
