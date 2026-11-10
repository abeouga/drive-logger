// 止まって静かか・動き出したかの判定（送信のきっかけ、送信の中断、待機からの起き上がりに使う）
#pragma once
#include <Arduino.h>

// 記録中：送るきっかけが来たら、その理由を返す（来ていなければ nullptr）。1 秒に 1 回呼ぶ
const char *uploadTrigger(uint32_t &quietSeconds);

// 記録を止めた後：ADXL345 の FIFO から 40 件読んで、ばらつきで動いているかを見る
bool movingNow();

// 動きが約 1 秒（300ms ごとに 3 回）続いたか。自動で始めた送信をやめるかの判定に使う
bool movingForAWhile();
