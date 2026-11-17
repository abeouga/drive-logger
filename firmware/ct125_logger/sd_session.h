// SD の 1 回の記録（/sessions/ride_NNN/）：フォルダーと meta.json・CSV の作成、リングバッファからの書き出し、status.csv
// ファイルと列の正式な定義は contracts/sd/
#pragma once
#include <Arduino.h>
#include <SD.h>

#include "freertos/ringbuf.h"
#include "sd_write_recovery.h"

extern String sessionDir;  // 例 /sessions/ride_012

// 記録中に開いたままの CSV。書けなくなったら開き直す（sd_write_recovery.h）
struct CsvFile {
  const char *name;  // 例 accel.csv
  File file;
  SdFileGuard guard;
};
extern CsvFile csvAccel, csvGps, csvEvent;
extern CsvFile csvEcu;  // ECU の値（V3.8。ECU を読む走行だけ開く）

// 起動時に、SD にある走行と accel.csv・gps.csv の大きさをシリアルに出す
void listSessions();

// 走行のフォルダーを作り、meta.json と 4 つの CSV（列の見出し付き）を書く。pendingEvents を events.csv に書く。
// ecu が true なら ecu.csv も作る（開けなくても記録は続ける）
bool openSession(bool ecu);

// リングバッファからたまった分（1 回 4KB まで）を取り出して c に書く。
// c が書けなくなっていて、まだ開き直せていなければ取り出さない（データはリングに残り、あふれたら ring_drops に数える）
void drain(RingbufHandle_t r, CsvFile &c, TickType_t wait);

// status.csv に 1 行足す（10 秒ごと・記録を閉じるとき）
void writeStatus();

// SD に書いている間だけ、呼んだタスクの優先度を SD_WRITE_PRIORITY に上げる（#132）。
// 加速度のタスクと同じコアで書くとき、書き込みの途中で割り込まれないようにするため（割り込まれると SD の書き込みが失敗する）。
// 診断：statSdUsMax は、この 10 秒で SD に書くのにかかった時間の最大（この間、加速度の読み出しは待たされる）
struct SdBoost {
  int64_t start;
  UBaseType_t old;
  SdBoost();
  ~SdBoost();
};
extern volatile int32_t statSdUsMax;
