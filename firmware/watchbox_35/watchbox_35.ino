// WatchBox 3.5" firmware: slot map, watch detail, settings and hotspot setup on the ESP32-32E board.
// Data comes from the Mac app's GET /api/box; the last good payload is cached so wake-up is instant.
#include <WiFi.h>
#include <driver/gpio.h>

#include "board.h"
#include "data.h"
#include "input.h"
#include "net.h"
#include "power.h"
#include "screens.h"
#include "theme.h"

LGFX tft;

enum class Screen { Home, Detail, Settings, ConfirmReset };

namespace {
const unsigned long FETCH_INTERVAL = 60000;
const unsigned long DETAIL_TIMEOUT = 30000;
const unsigned long STATUS_INTERVAL = 30000;
const unsigned long OFFLINE_AFTER = 20000;  // no Wi-Fi this long after boot -> offline banner

BoxData box;
BoxStatus status;
Screen screen = Screen::Home;
int detailIndex = 0;
String serverUrl, lastContent;  // lastContent: last payload without generated_at
unsigned long lastFetch = 0, lastStatus = 0, screenSince = 0;
bool fetchedThisBoot = false, needRedraw = true;
bool wasConnected = false;      // Wi-Fi state at the last tryFetch(): fetch at once on reconnect
bool drawnLowBattery = false;   // lowBattery as of the last full draw
}  // namespace

void refreshStatus() {
  int mv = power::batteryMv();
  status.batteryPct = power::batteryPct(mv);
  status.battery = status.batteryPct < 0 ? String("USB") : String(status.batteryPct) + "%";
  status.lowBattery = status.batteryPct >= 0 && status.batteryPct < 10;
  status.wifi = net::connected();
  status.updated = box.valid ? box.updated : String("");
}

void draw() {
  if (screen == Screen::Detail && !box.slots[detailIndex].present) screen = Screen::Home;  // left its slot
  refreshStatus();
  drawnLowBattery = status.lowBattery;
  switch (screen) {
    case Screen::Home:
      if (box.valid) screens::home(box, status);
      else screens::waiting(serverUrl, status);
      break;
    case Screen::Detail:
      screens::detail(box, detailIndex, status);
      break;
    case Screen::Settings:
      screens::settings(status, serverUrl, box.unslotted, WiFi.SSID(), WiFi.RSSI(), power::batteryMv());
      break;
    case Screen::ConfirmReset:
      screens::confirmReset();
      break;
  }
  needRedraw = false;
}

void show(Screen s) {
  screen = s;
  screenSince = millis();
  needRedraw = true;
}

int nextWatch(int from, int step) {
  for (int i = 1; i <= 8; i++) {
    int j = (from + step * i + 16) % 8;
    if (box.slots[j].present) return j;
  }
  return from;
}

void handleTouch(const TouchEvent& ev) {
  if (ev.gesture == Gesture::None) return;
  bool wasDimmed = power::noteActivity();
  screenSince = millis();  // the detail timeout counts from the last touch
  if (wasDimmed) return;   // the first touch on a dimmed screen only wakes it
  bool tap = ev.gesture == Gesture::Tap;
  switch (screen) {
    case Screen::Home:
      if (tap && screens::menuArea().contains(ev.x, ev.y)) {
        show(Screen::Settings);
        return;
      }
      if (tap && box.valid) {
        for (int i = 0; i < 8; i++) {
          if (box.slots[i].present && screens::tileArea(i).contains(ev.x, ev.y)) {
            detailIndex = i;
            show(Screen::Detail);
            return;
          }
        }
      }
      break;
    case Screen::Detail:
      if (ev.gesture == Gesture::SwipeLeft) {
        detailIndex = nextWatch(detailIndex, 1);
        show(Screen::Detail);
      } else if (ev.gesture == Gesture::SwipeRight) {
        detailIndex = nextWatch(detailIndex, -1);
        show(Screen::Detail);
      } else if (screens::backArea().contains(ev.x, ev.y)) {
        show(Screen::Home);
      }
      break;
    case Screen::Settings:
      if (!tap) break;
      if (screens::backArea().contains(ev.x, ev.y)) show(Screen::Home);
      else if (screens::resetButtonArea().contains(ev.x, ev.y)) show(Screen::ConfirmReset);
      break;
    case Screen::ConfirmReset:
      if (!tap) break;
      if (screens::confirmYesArea().contains(ev.x, ev.y)) {
        screens::setup(net::apName());
        net::resetAndRestart();
      } else if (screens::confirmNoArea().contains(ev.x, ev.y)) {
        show(Screen::Settings);
      }
      break;
  }
}

void tryFetch() {
  bool up = net::connected();
  bool reconnected = up && !wasConnected;
  wasConnected = up;
  if (!up) return;
  if (fetchedThisBoot && !reconnected && millis() - lastFetch < FETCH_INTERVAL) return;
  lastFetch = millis();
  fetchedThisBoot = true;
  String json;
  BoxData fresh;
  if (fetchBox(serverUrl, json) && parseBox(json, fresh)) {
    String content = boxContent(json);
    bool same = content == lastContent;
    bool changed = !same || status.offline;
    box = fresh;
    status.offline = false;
    if (!same) saveCache(json);
    lastContent = content;
    if (changed) needRedraw = true;
  } else if (!status.offline) {
    status.offline = true;
    needRedraw = true;
  }
}

void setup() {
  Serial.begin(115200);
  gpio_hold_dis(GPIO_NUM_27);  // released from the deep-sleep backlight hold
  tft.init();
  tft.setRotation(1);
  tft.setTouchCalibrate(TOUCH_CAL);
  tft.setBrightness(200);
  if (power::wokeFromTouch()) input::ignoreIfTouching();

  serverUrl = net::server();
  if (!net::configured()) net::runSetup(screens::setup);  // does not return

  String cached;
  if (loadCache(cached) && parseBox(cached, box)) lastContent = boxContent(cached);
  draw();  // instant: cached values (or "waiting for the app")
  net::begin();
  power::noteActivity();
}

void loop() {
  handleTouch(input::poll());
  net::maintain();
  tryFetch();

  if (!net::connected() && millis() > OFFLINE_AFTER && !status.offline) {
    status.offline = true;
    needRedraw = true;
  }
  if (screen == Screen::Detail && millis() - screenSince > DETAIL_TIMEOUT) show(Screen::Home);
  if (millis() - lastStatus > STATUS_INTERVAL) {
    lastStatus = millis();
    refreshStatus();
    if (status.lowBattery != drawnLowBattery) needRedraw = true;  // banner appears or goes
    else if (screen == Screen::Home && box.valid && !needRedraw) screens::homeStatusBar(status);
  }
  if (power::update(status.batteryPct < 0) == power::Action::Sleep) power::sleepNow();
  if (needRedraw) draw();
  delay(10);
}
