#pragma once
#include <Arduino.h>

struct WatchInfo {
  bool present = false;
  int slot = 0;
  String name, brand, reference, details, confidence, asOf;
  bool hasEstimate = false;
  long estimate = 0;
  bool estimatedRef = false;
  int ebayN = 0;
  bool hasEbay = false;
  long ebayMedian = 0, ebayP10 = 0, ebayP90 = 0;
  int c24N = 0;
  bool hasC24 = false;
  long c24Median = 0;
  int accN = 0;
  bool hasAcc = false;
  float mdape = 0;
};

struct BoxData {
  bool valid = false;
  long total = 0;
  int priced = 0;
  int unslotted = 0;
  String updated;  // "Oct 2, 1:14 PM", from the server
  WatchInfo slots[8];
};

bool parseBox(const String& json, BoxData& out);     // false if not a valid 8-slot payload
bool fetchBox(const String& server, String& json);   // true on HTTP 200 with a body
void saveCache(const String& json);
bool loadCache(String& json);
String boxContent(const String& json);  // payload minus "generated_at" (changes every request)
