// GPS（ATGM336H）のタスク：NMEA の RMC・GGA を読み、gps.csv の 1 行をリングバッファに入れる（1Hz）
#pragma once
#include <Arduino.h>

extern volatile char gpsStatus;     // RMC の状態（'A'＝有効、'V'＝無効）
extern volatile int gpsSats;        // GGA の衛星数
extern volatile int64_t ppsUs;      // PPS の立ち上がりの時刻（PIN_PPS を使うときだけ）
extern volatile float gpsSpeedKmh;  // GPS 速度（無効なら -1）。送信のきっかけの判定に使う

void onPps();  // 本体は gps_task.cpp で IRAM_ATTR を付ける（割り込みから呼ぶ）

// stopRequested が立つまで回る（xTaskCreatePinnedToCore に渡す）
void gpsTask(void *);
