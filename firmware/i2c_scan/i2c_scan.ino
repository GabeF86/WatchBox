// Prints the address of every I2C device (the LCD backpack is usually 0x27 or 0x3F).
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin();  // ESP32 defaults: SDA = GPIO21, SCL = GPIO22
}

void loop() {
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("I2C device at 0x%02X\n", addr);
      found++;
    }
  }
  if (found == 0) Serial.println("No I2C devices found - check SDA/SCL wiring");
  Serial.println("---");
  delay(3000);
}
