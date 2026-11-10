#include "boot_button.h"

#include "logger_constants.h"

bool buttonHeld() {
  static uint32_t pressedAt = 0;
  static bool fired = false;
  if (digitalRead(PIN_BOOT) == HIGH) {
    pressedAt = 0;
    fired = false;
    return false;
  }
  if (pressedAt == 0) pressedAt = millis();
  if (!fired && millis() - pressedAt >= BUTTON_HOLD_MS) {
    fired = true;
    return true;
  }
  return false;
}
