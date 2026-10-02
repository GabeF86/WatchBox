#pragma once
#include <Arduino.h>

// "$13,650"; from a million up "$1.2M".
inline String formatPrice(long usd) {
  if (usd >= 1000000) {
    char buf[16];
    snprintf(buf, sizeof buf, "$%.1fM", usd / 1000000.0);
    return String(buf);
  }
  String digits = String(usd);
  String out = "$";
  int n = digits.length();
  for (int i = 0; i < n; i++) {
    out += digits[i];
    int rest = n - 1 - i;
    if (rest > 0 && rest % 3 == 0) out += ',';
  }
  return out;
}

// "$10.5k" for compact ranges; under $1,000 stays "$950".
inline String formatK(long usd) {
  if (usd < 1000) return "$" + String(usd);
  char buf[16];
  snprintf(buf, sizeof buf, "$%.1fk", usd / 1000.0);
  return String(buf);
}
