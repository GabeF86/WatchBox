#include "input.h"

#include <stdlib.h>

#include "board.h"

namespace {
const int SWIPE_MIN = 60;    // px of horizontal travel for a swipe
const int RELEASE_POLLS = 3; // resistive touch flickers; require a few empty reads before "lifted"
bool down = false, ignoring = false;
int startX = 0, startY = 0, lastX = 0, lastY = 0, emptyPolls = 0;
}  // namespace

void input::ignoreIfTouching() {
  int32_t x, y;
  if (tft.getTouch(&x, &y)) {
    down = true;
    ignoring = true;
    startX = lastX = x;
    startY = lastY = y;
  }
}

TouchEvent input::poll() {
  TouchEvent ev;
  int32_t x, y;
  if (tft.getTouch(&x, &y)) {
    if (!down) {
      down = true;
      startX = x;
      startY = y;
    }
    lastX = x;
    lastY = y;
    emptyPolls = 0;
    return ev;
  }
  if (!down || ++emptyPolls < RELEASE_POLLS) return ev;
  down = false;
  emptyPolls = 0;
  if (ignoring) {
    ignoring = false;
    return ev;
  }
  int dx = lastX - startX, dy = lastY - startY;
  if (abs(dx) >= SWIPE_MIN && abs(dx) > abs(dy)) ev.gesture = dx < 0 ? Gesture::SwipeLeft : Gesture::SwipeRight;
  else ev.gesture = Gesture::Tap;
  ev.x = startX;
  ev.y = startY;
  return ev;
}
