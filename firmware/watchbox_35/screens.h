#pragma once
#include <Arduino.h>

#include "data.h"

struct Area {
  int x, y, w, h;
  bool contains(int px, int py) const { return px >= x && px < x + w && py >= y && py < y + h; }
};

struct BoxStatus {
  bool wifi = false;
  String battery;       // "82%" or "USB"
  int batteryPct = -1;  // -1 on USB power
  String updated;       // "Oct 2, 1:14 PM" or ""
  bool offline = false;
  bool lowBattery = false;
};

namespace screens {
Area tileArea(int index);  // 0..7, slot = index + 1
Area menuArea();           // status-bar menu icon
Area backArea();           // status-bar "< Back"
Area resetButtonArea();    // settings: "Re-run setup"
Area confirmYesArea();
Area confirmNoArea();

void home(const BoxData& d, const BoxStatus& s);
void homeStatusBar(const BoxStatus& s);  // redraw only the status bar on the home screen
void detail(const BoxData& d, int index, const BoxStatus& s);
void settings(const BoxStatus& s, const String& server, int unslotted, const String& ssid, int rssi, int batteryMv);
void confirmReset();
void setup(const String& apName);
void waiting(const String& server, const BoxStatus& s);
}  // namespace screens
