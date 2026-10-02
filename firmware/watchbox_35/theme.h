#pragma once
#include <stdint.h>

constexpr uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

namespace theme {
constexpr uint16_t BG = rgb(0x0B, 0x0C, 0x0E);
constexpr uint16_t TILE = rgb(0x16, 0x19, 0x1E);
constexpr uint16_t TEXT = rgb(0xE9, 0xE9, 0xE9);
constexpr uint16_t MUTED = rgb(0x8B, 0x90, 0x99);
constexpr uint16_t LINE = rgb(0x2A, 0x2E, 0x35);
constexpr uint16_t GOLD = rgb(0xF2, 0xC4, 0x6D);
constexpr uint16_t CONF_HIGH = rgb(0x5F, 0xD1, 0x8B);
constexpr uint16_t CONF_MEDIUM = rgb(0xE7, 0xC1, 0x60);
constexpr uint16_t CONF_LOW = rgb(0xE0, 0x7A, 0x6A);
constexpr uint16_t NONE = rgb(0x55, 0x5A, 0x62);
constexpr uint16_t WARN_BG = rgb(0x3A, 0x2E, 0x12);
constexpr uint16_t BUTTON = rgb(0x24, 0x28, 0x30);
constexpr uint16_t WHITE = rgb(0xFF, 0xFF, 0xFF);

constexpr int W = 480, H = 320, BAR_H = 24, MARGIN = 10, GAP = 6;
constexpr int GRID_TOP = 80;
constexpr int TILE_W = (W - 2 * MARGIN - 3 * GAP) / 4;     // 110
constexpr int TILE_H = (H - GRID_TOP - MARGIN - GAP) / 2;  // 112
}  // namespace theme
