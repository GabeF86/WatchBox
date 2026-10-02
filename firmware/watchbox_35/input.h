#pragma once

enum class Gesture { None, Tap, SwipeLeft, SwipeRight };

struct TouchEvent {
  Gesture gesture = Gesture::None;
  int x = 0, y = 0;
};

namespace input {
void ignoreIfTouching();  // after waking from sleep: the waking touch is not a tap
TouchEvent poll();        // call every loop; reports a gesture when the finger lifts
}  // namespace input
