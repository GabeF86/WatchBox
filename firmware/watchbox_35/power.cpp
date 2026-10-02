#include "power.h"

#include <WiFi.h>
#include <driver/gpio.h>
#include <esp_sleep.h>

#include "board.h"

namespace {
const unsigned long DIM_AFTER_BATTERY = 120000;  // 2 min
const unsigned long DIM_AFTER_USB = 600000;      // 10 min
const unsigned long SLEEP_AFTER_DIM = 15000;
const uint8_t BRIGHT = 200, DIMMED = 30;
const int BATTERY_PIN = 34;
const int BACKLIGHT_PIN = 27;  // GPIO_NUM_27 in sleepNow() and setup()
unsigned long lastActivity = 0;
bool dimmed = false;
}  // namespace

int power::batteryMv() { return analogReadMilliVolts(BATTERY_PIN) * 2; }

bool power::onUsb(int mv) { return mv < 2500 || mv > 4500; }

int power::batteryPct(int mv) {
  if (onUsb(mv)) return -1;
  long pct = map(mv, 3300, 4150, 0, 100);
  return constrain(pct, 0L, 100L);
}

bool power::wokeFromTouch() { return esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT0; }

bool power::noteActivity() {
  lastActivity = millis();
  if (!dimmed) return false;
  dimmed = false;
  tft.setBrightness(BRIGHT);
  return true;
}

power::Action power::update(bool usb) {
  unsigned long idle = millis() - lastActivity;
  unsigned long dimAfter = usb ? DIM_AFTER_USB : DIM_AFTER_BATTERY;
  if (!dimmed && idle >= dimAfter) {
    dimmed = true;
    tft.setBrightness(DIMMED);
    return Action::Dim;
  }
  if (dimmed && idle >= dimAfter + SLEEP_AFTER_DIM) return Action::Sleep;
  return Action::None;
}

void power::sleepNow() {
  tft.setBrightness(0);
  tft.sleep();  // also sets brightness 0 via the PWM, so the pin is taken over after it
  pinMode(BACKLIGHT_PIN, OUTPUT);  // hold the backlight off: the PWM stops in deep sleep and the pin would float
  digitalWrite(BACKLIGHT_PIN, LOW);
  gpio_hold_en(GPIO_NUM_27);
  gpio_deep_sleep_hold_en();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  esp_sleep_enable_ext0_wakeup(GPIO_NUM_36, 0);  // XPT2046 pen interrupt goes low on touch
  esp_deep_sleep_start();
}
