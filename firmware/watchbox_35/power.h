#pragma once
#include <Arduino.h>

namespace power {
enum class Action { None, Dim, Sleep };
int batteryMv();         // via the board's 1:2 divider on IO34 (verify with a multimeter)
bool onUsb(int mv);      // implausible reading = no battery fitted -> USB power
int batteryPct(int mv);  // -1 on USB
bool wokeFromUser();      // woken by a touch (IO36) or the BOOT button (IO0)
void backlightOn();      // full brightness; setup() calls it after the first frame
bool isDimmed();
bool noteActivity();     // any touch: resets the idle timer and undims; true if the screen was dimmed
Action update(bool usb); // call every loop
void sleepNow();         // deep sleep until the screen is touched or BOOT pressed; does not return
}  // namespace power
