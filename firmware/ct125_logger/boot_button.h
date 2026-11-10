// BOOT ボタン（IO0）の長押し
#pragma once
#include <Arduino.h>

// 押し続けて BUTTON_HOLD_MS を超えたら 1 回だけ true（離すまで次は来ない）
bool buttonHeld();
