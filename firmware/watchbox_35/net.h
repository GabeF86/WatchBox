#pragma once
#include <Arduino.h>

namespace net {
String apName();                                     // "WatchBox-XXXX"
String server();                                     // saved app address, "" if none
bool configured();                                   // Wi-Fi and app address saved
void runSetup(void (*onPortal)(const String& ap));  // blocking hotspot setup; restarts when done
void begin();                                        // connect with saved credentials (non-blocking)
bool connected();
void maintain();                                     // reconnect attempt every 30 s while offline
void resetAndRestart();                              // forget Wi-Fi + app address, restart into setup
}  // namespace net
