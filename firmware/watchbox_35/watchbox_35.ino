#include "board.h"
#include "format.h"
#include "theme.h"

LGFX tft;

void setup() {
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(theme::BG);
  tft.setTextColor(theme::GOLD);
  tft.setFont(&fonts::FreeSansBold24pt7b);
  tft.drawString(formatPrice(39130).c_str(), 20, 20);
}

void loop() {}
