// SD の 1 回の記録（/sessions/ride_NNN/）：フォルダーと meta.json・CSV の作成、リングバッファからの書き出し、status.csv
// ファイルと列の正式な定義は contracts/sd/
#pragma once
#include <Arduino.h>
#include <SD.h>

#include "freertos/ringbuf.h"

extern String sessionDir;           // 例 /sessions/ride_012
extern File fAccel, fGps, fEvent;   // 記録中に開いたままの CSV

// 起動時に、SD にある走行と accel.csv・gps.csv の大きさをシリアルに出す
void listSessions();

// 走行のフォルダーを作り、meta.json と 4 つの CSV（列の見出し付き）を書く。pendingEvents を events.csv に書く
bool openSession();

// リングバッファからたまった分（1 回 4KB まで）を取り出して f に書く
void drain(RingbufHandle_t r, File &f, TickType_t wait);

// status.csv に 1 行足す（10 秒ごと・記録を閉じるとき）
void writeStatus();
