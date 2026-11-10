// シリアルのコマンド（設定と、手動の送信）
// CFG ...（config_store.cpp）、UPLOAD（BOOT ボタンと同じ）、LOG（送信の記録の最後の 40 行）を受け付ける。
#pragma once
#include <Arduino.h>

// UPLOAD が届いたら立つ。受けた側（loopLogging・loopIdle）が下ろす
extern bool uploadRequestedBySerial;

// 記録を止めないよう、届いた分だけ読む。loop() から毎回呼ぶ
void pollSerial();
