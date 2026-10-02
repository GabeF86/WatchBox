#pragma once
#include <Arduino.h>

namespace power {
enum class Action { None, Dim, Sleep };
int batteryMv();         // via the board's 1:2 divider on IO34 (verify with a multimeter)
bool onUsb(int mv);      // implausible reading = no battery fitted -> USB power
int batteryPct(int mv);  // -1 on USB
bool wokeFromTouch();
bool noteActivity();     // any touch: resets the idle timer and undims; true if the screen was dimmed
Action update(bool usb); // call every loop
void sleepNow();         // deep sleep until the screen is touched; does not return
}  // namespace power
