#include "data.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Preferences.h>

#include <memory>

namespace {
const char* NS = "watchbox";
const size_t MAX_CACHE = 6000;

void readWatch(JsonObjectConst w, int slot, WatchInfo& out) {
  out = WatchInfo();
  out.present = true;
  out.slot = slot;
  out.name = w["name"] | "";
  out.brand = w["brand"] | "";
  out.reference = w["reference"] | "";
  out.details = w["details"] | "";
  out.confidence = w["confidence"] | "";
  out.asOf = w["as_of_label"] | "";
  out.hasEstimate = !w["estimate_usd"].isNull();
  out.estimate = w["estimate_usd"] | 0L;
  out.estimatedRef = w["estimated_reference"] | false;
  JsonObjectConst e = w["ebay"];
  out.ebayN = e["n"] | 0;
  out.hasEbay = !e["median"].isNull();
  out.ebayMedian = e["median"] | 0L;
  out.ebayP10 = e["p10"] | 0L;
  out.ebayP90 = e["p90"] | 0L;
  JsonObjectConst c = w["chrono24"];
  out.c24N = c["n"] | 0;
  out.hasC24 = !c["median"].isNull();
  out.c24Median = c["median"] | 0L;
  JsonObjectConst a = w["accuracy"];
  out.accN = a["n"] | 0;
  out.hasAcc = !a["mdape"].isNull();
  out.mdape = a["mdape"] | 0.0f;
}
}  // namespace

bool parseBox(const String& json, BoxData& out) {
  JsonDocument doc;
  if (deserializeJson(doc, json)) return false;
  JsonArrayConst slots = doc["slots"];
  if (slots.isNull() || slots.size() != 8) return false;
  BoxData fresh;
  fresh.total = doc["total_usd"] | 0L;
  fresh.priced = doc["priced"] | 0;
  fresh.unslotted = doc["unslotted"].as<JsonArrayConst>().size();
  fresh.updated = doc["updated_label"] | "";
  for (size_t i = 0; i < 8; i++) {
    JsonObjectConst s = slots[i];
    if (!s["watch"].isNull()) {
      readWatch(s["watch"], s["slot"] | int(i + 1), fresh.slots[i]);
    } else {
      fresh.slots[i] = WatchInfo();
      fresh.slots[i].slot = i + 1;
    }
  }
  fresh.valid = true;
  out = fresh;
  return true;
}

bool fetchBox(const String& server, String& json) {
  HTTPClient http;
  if (!http.begin(server + "/api/box")) return false;
  http.useHTTP10(true);
  http.setConnectTimeout(3000);
  http.setTimeout(5000);
  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    Serial.printf("GET /api/box failed: %d\n", code);
    http.end();
    return false;
  }
  json = http.getString();
  http.end();
  return json.length() > 0;
}

void saveCache(const String& json) {
  if (json.length() > MAX_CACHE) {
    Serial.println("cache: payload too large, not cached");
    return;
  }
  Preferences p;
  if (!p.begin(NS, false)) {
    Serial.println("cache: NVS open failed");
    return;
  }
  if (p.putBytes("box", json.c_str(), json.length()) != json.length()) Serial.println("cache: write failed");
  p.end();
}

bool loadCache(String& json) {
  Preferences p;
  if (!p.begin(NS, true)) return false;
  size_t n = p.getBytesLength("box");
  if (n == 0 || n > MAX_CACHE) {
    p.end();
    return false;
  }
  std::unique_ptr<char[]> buf(new char[n + 1]);
  p.getBytes("box", buf.get(), n);
  buf[n] = 0;
  p.end();
  json = String(buf.get());
  return true;
}

String boxContent(const String& json) {
  int k = json.indexOf("\"generated_at\"");
  int end = k < 0 ? -1 : json.indexOf(',', k);
  if (end < 0) return json;
  return json.substring(0, k) + json.substring(end + 1);
}
