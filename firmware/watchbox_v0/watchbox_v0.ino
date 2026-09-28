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
