#include "net.h"

#include <Preferences.h>
#include <WiFi.h>
#include <WiFiManager.h>

namespace {
const char* NS = "watchbox";
const char* DEFAULT_SERVER = "http://watchbox.local:8000";
unsigned long lastAttempt = 0;
void (*portalCallback)(const String&) = nullptr;

void saveServer(const String& s) {
  Preferences p;
  p.begin(NS, false);
  p.putString("server", s);
  p.end();
}
}  // namespace

String net::apName() {
  char buf[20];
  snprintf(buf, sizeof buf, "WatchBox-%04X", (unsigned)((ESP.getEfuseMac() >> 32) & 0xFFFF));
  return String(buf);
}

String net::server() {
  Preferences p;
  p.begin(NS, true);
  String s = p.getString("server", "");
  p.end();
  return s;
}

bool net::configured() {
  WiFi.mode(WIFI_STA);  // getWiFiIsSaved() reads the STA config, which needs Wi-Fi initialised
  WiFiManager wm;
  return wm.getWiFiIsSaved() && server().length() > 0;
}

void net::runSetup(void (*onPortal)(const String& ap)) {
  portalCallback = onPortal;
  String current = server();
  if (!current.length()) current = DEFAULT_SERVER;
  WiFiManager wm;
  WiFiManagerParameter serverField("server", "App address (e.g. http://192.168.1.50:8000)", current.c_str(), 80);
  wm.addParameter(&serverField);
  wm.setTitle("WatchBox setup");
  wm.setConfigPortalTimeout(600);
  wm.setAPCallback([](WiFiManager*) {
    if (portalCallback) portalCallback(net::apName());
  });
  String ap = apName();
  if (onPortal) onPortal(ap);
  if (wm.startConfigPortal(ap.c_str())) {
    String s = serverField.getValue();
    s.trim();
    while (s.endsWith("/")) s.remove(s.length() - 1);
    saveServer(s);
  }
  ESP.restart();
}

void net::begin() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin();  // credentials saved by WiFiManager
  lastAttempt = millis();
}

bool net::connected() { return WiFi.status() == WL_CONNECTED; }

void net::maintain() {
  if (!connected() && millis() - lastAttempt > 30000) {
    lastAttempt = millis();
    WiFi.reconnect();
  }
}

void net::resetAndRestart() {
  WiFiManager wm;
  wm.resetSettings();
  Preferences p;
  p.begin(NS, false);
  p.remove("server");
  p.remove("box");
  p.end();
  ESP.restart();
}
