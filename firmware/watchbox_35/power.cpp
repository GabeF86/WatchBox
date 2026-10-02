#include "power.h"

#include <WiFi.h>
#include <driver/gpio.h>
#include <esp_sleep.h>

#include "board.h"

namespace {
const unsigned long DIM_AFTER_BATTERY = 120000;  // 2 min
const unsigned long DIM_AFTER_USB = 600000;      // 10 min
const unsigned long SLEEP_AFTER_DIM = 15000;
const uint8_t BRIGHT = 200, DIMMED = 38;  // dimmed is about 15%
const int BATTERY_PIN = 34;
const int BACKLIGHT_PIN = 27;  // held low in deep sleep (GPIO_NUM_27)
const int LCD_CS_PIN = 15, TOUCH_CS_PIN = 33;  // held high in deep sleep so neither chip sees a select
const int TOUCH_IRQ_PIN = 36;
unsigned long lastActivity = 0, lastIrqLog = 0;
bool dimmed = false;
}  // namespace

int power::batteryMv() { return analogReadMilliVolts(BATTERY_PIN) * 2; }

bool power::onUsb(int mv) { return mv < 2500 || mv > 4500; }

int power::batteryPct(int mv) {
  if (onUsb(mv)) return -1;
  long pct = map(mv, 3300, 4150, 0, 100);
  return constrain(pct, 0L, 100L);
}

bool power::wokeFromUser() {
  esp_sleep_wakeup_cause_t c = esp_sleep_get_wakeup_cause();
  return c == ESP_SLEEP_WAKEUP_EXT0 || c == ESP_SLEEP_WAKEUP_EXT1;
}

void power::backlightOn() { tft.setBrightness(BRIGHT); }

bool power::isDimmed() { return dimmed; }

bool power::noteActivity() {
  lastActivity = millis();
  if (!dimmed) return false;
  dimmed = false;
  tft.setBrightness(BRIGHT);
  return true;
}

power::Action power::update(bool usb) {
#ifdef DEMO_ALWAYS_ON  // demo build: never dim or sleep (keeps a power bank from switching off)
  (void)usb;
  return Action::None;
#endif
  unsigned long idle = millis() - lastActivity;
  unsigned long dimAfter = usb ? DIM_AFTER_USB : DIM_AFTER_BATTERY;
  if (!dimmed && idle >= dimAfter) {
    dimmed = true;
    tft.setBrightness(DIMMED);
    return Action::Dim;
  }
  if (dimmed && millis() - lastIrqLog >= 10000) {  // bring-up diagnostics: IO36 should idle HIGH
    lastIrqLog = millis();
    Serial.printf("irq36 idle=%d\n", digitalRead(TOUCH_IRQ_PIN));
  }
  if (dimmed && idle >= dimAfter + SLEEP_AFTER_DIM) {
    if (digitalRead(TOUCH_IRQ_PIN) == LOW) {  // finger on the screen, or the line floats low: it would wake at once
      Serial.println("sleep postponed: irq36 is LOW");
      lastActivity = millis() - dimAfter;  // stay dimmed and try again after SLEEP_AFTER_DIM
      return Action::None;
    }
    return Action::Sleep;
  }
  return Action::None;
}

void power::sleepNow() {
  tft.setBrightness(0);
  tft.sleep();  // also sets brightness 0 via the PWM, so the pin is taken over after it
  pinMode(BACKLIGHT_PIN, OUTPUT);  // hold the backlight off: the PWM stops in deep sleep and the pin would float
  digitalWrite(BACKLIGHT_PIN, LOW);
  pinMode(LCD_CS_PIN, OUTPUT);
  digitalWrite(LCD_CS_PIN, HIGH);
  pinMode(TOUCH_CS_PIN, OUTPUT);
  digitalWrite(TOUCH_CS_PIN, HIGH);
  gpio_hold_en(GPIO_NUM_27);
  gpio_hold_en(GPIO_NUM_15);
  gpio_hold_en(GPIO_NUM_33);
  gpio_deep_sleep_hold_en();  // setup() releases all three with gpio_hold_dis()
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  esp_sleep_enable_ext0_wakeup(GPIO_NUM_36, 0);  // XPT2046 pen interrupt goes low on touch
  esp_sleep_enable_ext1_wakeup(1ULL << GPIO_NUM_0, ESP_EXT1_WAKEUP_ALL_LOW);  // BOOT button: a fallback wake
  esp_deep_sleep_start();
}
