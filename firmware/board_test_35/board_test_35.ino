// Bring-up test for the ESP32-32E 3.5" board (ST7796 320x480, XPT2046 resistive touch).
// 1. Color bars + text   -> the display works, colors are right
// 2. Wi-Fi + /api/display -> your watches from the Mac app, all on one screen
// 3. Touch               -> a dot where you touch; raw coordinates on Serial (115200)
//    Hold BOOT for ~1 s to run touch calibration (tap the 4 corner arrows); values print to Serial.
// Uses config.h (WIFI_SSID, WIFI_PASS, SERVER_URL), same as the watchbox_v0 sketch; LCD_ADDR is ignored.
#define LGFX_USE_V1
#include <LovyanGFX.hpp>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

#ifndef COLOR_INVERT
#define COLOR_INVERT false
#endif
#ifndef COLOR_BGR
#define COLOR_BGR false
#endif

class LGFX : public lgfx::LGFX_Device {
  lgfx::Panel_ST7796 panel_;
  lgfx::Bus_SPI bus_;
  lgfx::Light_PWM light_;
  lgfx::Touch_XPT2046 touch_;

 public:
  LGFX() {
    {
      auto cfg = bus_.config();
      cfg.spi_host = HSPI_HOST;
      cfg.spi_mode = 0;
      cfg.freq_write = 20000000;  // 40 MHz garbled colors on this panel
      cfg.freq_read = 16000000;
      cfg.spi_3wire = false;
      cfg.use_lock = true;
      cfg.dma_channel = SPI_DMA_CH_AUTO;
      cfg.pin_sclk = 14;
      cfg.pin_mosi = 13;
      cfg.pin_miso = 12;
      cfg.pin_dc = 2;
      bus_.config(cfg);
      panel_.setBus(&bus_);
    }
    {
      auto cfg = panel_.config();
      cfg.pin_cs = 15;
      cfg.pin_rst = -1;  // shared with the ESP32 EN line
      cfg.pin_busy = -1;
      cfg.panel_width = 320;
      cfg.panel_height = 480;
      cfg.readable = true;
      cfg.invert = COLOR_INVERT;
      cfg.rgb_order = COLOR_BGR;
      cfg.bus_shared = true;
      panel_.config(cfg);
    }
    {
      auto cfg = light_.config();
      cfg.pin_bl = 27;
      cfg.invert = false;
      cfg.freq = 44100;
      cfg.pwm_channel = 7;
      light_.config(cfg);
      panel_.setLight(&light_);
    }
    {
      auto cfg = touch_.config();
      cfg.x_min = 300;  // typical XPT2046 raw range; calibration (BOOT) refines it
      cfg.x_max = 3900;
      cfg.y_min = 200;
      cfg.y_max = 3900;
      cfg.pin_int = 36;
      cfg.bus_shared = true;
      cfg.spi_host = HSPI_HOST;
      cfg.freq = 1000000;
      cfg.pin_sclk = 14;
      cfg.pin_mosi = 13;
      cfg.pin_miso = 12;
      cfg.pin_cs = 33;
      touch_.config(cfg);
      panel_.setTouch(&touch_);
    }
    setPanel(&panel_);
  }
};

LGFX tft;

// Measured on the owner's board (BOOT-held calibration, 2026-10-02).
uint16_t touchCal[8] = {378, 3815, 333, 301, 3689, 3781, 3687, 332};

const int BOOT_KEY = 0;
const uint32_t BG = TFT_BLACK;

void title(const char* text) {
  tft.fillScreen(BG);
  tft.setTextColor(TFT_WHITE, BG);
  tft.setFont(&fonts::FreeSansBold12pt7b);
  tft.setCursor(16, 14);
  tft.print(text);
}

void drawBars(int option) {
  const uint32_t colors[] = {TFT_RED, TFT_GREEN, TFT_BLUE, TFT_WHITE};
  const char* names[] = {"RED", "GREEN", "BLUE", "WHITE"};
  int w = tft.width() / 4;
  for (int i = 0; i < 4; i++) {
    tft.fillRect(i * w, 0, w, tft.height(), colors[i]);
    tft.setTextColor(TFT_BLACK, colors[i]);
    tft.setFont(&fonts::FreeSansBold12pt7b);
    tft.setCursor(i * w + 12, tft.height() / 2);
    tft.print(names[i]);
  }
  tft.fillRect(tft.width() / 2 - 40, 20, 80, 70, TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setFont(&fonts::FreeSansBold24pt7b);
  tft.setCursor(tft.width() / 2 - 14, 30);
  tft.print(option);
}

void colorTest() {
  Serial.printf("color test: invert=%d bgr=%d\n", (int)COLOR_INVERT, (int)COLOR_BGR);
  drawBars(1 + (COLOR_INVERT ? 1 : 0) + (COLOR_BGR ? 2 : 0));
  delay(2500);
}

bool connectWifi() {
  title("Connecting to Wi-Fi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) delay(250);
  if (WiFi.status() != WL_CONNECTED) {
    title("Wi-Fi failed");
    tft.setFont(&fonts::FreeSans9pt7b);
    tft.setCursor(16, 60);
    tft.printf("status %d - check config.h (2.4 GHz)", WiFi.status());
    return false;
  }
  Serial.printf("WiFi connected, IP %s\n", WiFi.localIP().toString().c_str());
  return true;
}

void showWatches() {
  HTTPClient http;
  http.useHTTP10(true);
  http.setConnectTimeout(3000);
  http.setTimeout(5000);
  http.begin(String(SERVER_URL) + "/api/display");
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    title("Mac app not reachable");
    tft.setFont(&fonts::FreeSans9pt7b);
    tft.setCursor(16, 60);
    tft.printf("HTTP %d from %s", code, SERVER_URL);
    http.end();
    return;
  }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getStream());
  http.end();
  if (err) {
    title("Bad response");
    return;
  }
  JsonArray screens = doc["screens"].as<JsonArray>();
  tft.fillScreen(BG);
  int y = 12;
  bool first = true;
  for (JsonObject s : screens) {
    const char* l1 = s["line1"] | "";
    const char* l2 = s["line2"] | "";
    if (first) {  // TOTAL line, big and gold
      tft.setTextColor(0xFEA0, BG);
      tft.setFont(&fonts::FreeSansBold18pt7b);
      tft.setCursor(16, y);
      tft.print(l2);
      tft.setFont(&fonts::FreeSans9pt7b);
      tft.setTextColor(TFT_LIGHTGREY, BG);
      tft.setCursor(16, y + 44);
      tft.print(l1);
      y += 80;
      tft.drawFastHLine(16, y - 12, tft.width() - 32, TFT_DARKGREY);
      first = false;
      continue;
    }
    tft.setFont(&fonts::FreeSans12pt7b);
    tft.setTextColor(TFT_WHITE, BG);
    tft.setCursor(16, y);
    tft.print(l1);
    tft.setTextColor(TFT_GREENYELLOW, BG);
    tft.setTextDatum(top_right);
    tft.drawString(l2, tft.width() - 16, y);
    tft.setTextDatum(top_left);
    y += 40;
  }
  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setTextColor(TFT_DARKGREY, BG);
  tft.setCursor(16, tft.height() - 24);
  tft.print("Touch anywhere - dots should appear under your finger");
}

void calibrate() {
  title("Touch calibration");
  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setCursor(16, 50);
  tft.print("Tap each arrow as it appears");
  delay(1200);
  uint16_t cal[8];
  tft.calibrateTouch(cal, (uint32_t)TFT_WHITE, BG, 20);
  Serial.print("Touch calibration: {");
  for (int i = 0; i < 8; i++) Serial.printf("%u%s", cal[i], i < 7 ? ", " : "}\n");
  tft.setTouchCalibrate(cal);
  showWatches();
}

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_KEY, INPUT_PULLUP);
  Serial.println("init display");
  tft.init();
  Serial.println("display ok");
  tft.setRotation(1);
  tft.setTouchCalibrate(touchCal);  // landscape, 480 x 320
  tft.setBrightness(200);
  colorTest();
  if (connectWifi()) showWatches();
}

void loop() {
  int32_t x, y;
  if (tft.getTouch(&x, &y)) {
    tft.fillCircle(x, y, 4, TFT_CYAN);
    Serial.printf("touch %ld,%ld\n", (long)x, (long)y);
  }
  static unsigned long bootDown = 0;
  if (digitalRead(BOOT_KEY) == LOW) {
    if (!bootDown) bootDown = millis();
    if (millis() - bootDown > 1000) {
      bootDown = 0;
      calibrate();
    }
  } else {
    bootDown = 0;
  }
  delay(10);
}
