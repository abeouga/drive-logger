// 動作の状態と、タスクをまたいで読み書きする値（件数・止める合図・リングバッファ）。
// 実体は logger_state.cpp。どのタスクが書くかは各行のコメントのとおり
#pragma once
#include <Arduino.h>

#include "esp_timer.h"
#include "freertos/ringbuf.h"
#include "uploader.h"

// 動作の状態
// MODE_WAIT_ADXL：SD はあるが、起動時に ADXL345 が無かった。1 秒ごとに探し、待っている間に送り残しを送る（V3.6）
enum Mode { MODE_ERROR, MODE_LOGGING, MODE_UPLOADING, MODE_IDLE, MODE_WAIT_ADXL };
extern volatile Mode mode;
extern volatile UploadResult lastUploadResult;
// ADXL345 を待っている間に、送り残しを送ろうとしたか（LED で結果を見せるため）
extern volatile bool waitUploadTried;

static inline int64_t nowUs() { return esp_timer_get_time(); }

// ファイルごとのリングバッファ（加速度は大きく、ほかは小さく）。setup() が作り、finishSession() が消す
extern RingbufHandle_t ringAccel, ringGps, ringEvent;

// 記録の件数とエラーの数（status.csv に書く）
extern volatile uint32_t samples, ringDrops, fifoOverruns, i2cErrors, sdWriteErrors;
extern volatile uint64_t bytesWritten;
extern volatile int64_t firstSampleUs, lastSampleUs;
extern bool running;  // セッションのファイルが開いていて、リングバッファがある

// 記録を閉じるとき、加速度と GPS のタスクに止まってもらう
extern volatile bool stopRequested, accelStopped, gpsStopped;
// この走行で一度でも動いたか（止まったまま電源を入れただけの走行は閉じない）。sensorTask・gpsTask が立てる
extern volatile bool hasMoved;
// 記録中に ADXL345 が外れたとみなしている（sensorTask が立て、戻ったら下ろす。静かの判定が読む）
extern volatile bool accelLost;
