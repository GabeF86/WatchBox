#pragma once
// Copy to config.h (gitignored) and fill in.
#define WIFI_SSID  "your-wifi-name"              // 2.4 GHz network; the ESP32 can't join 5 GHz
#define WIFI_PASS  "your-wifi-password"
#define SERVER_URL "http://192.168.1.50:8000"    // "ESP32 SERVER_URL" printed by the server at startup
#define LCD_ADDR   0x27                          // from the i2c_scan sketch (0x27 or 0x3F)
