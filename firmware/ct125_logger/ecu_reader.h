// ECU の値の読み出し（V3.8）。市販の ELM327 互換アダプターに BLE（NimBLE。サービス FFF0、FFF2 に書き FFF1 の通知で受ける）でつなぎ、
// OBD のモード 01 の要求を順番に送って、ecu.csv 用のリングバッファに 1 行ずつ足す（docs/analysis_policy.md 1.3）。
// 送る命令は elm_parse.h の allowedCommand() で縛る。アダプターのアドレスは CFG SET ecu_addr で NVS に置く。
// 記録中だけ動き、記録を閉じるときに BLE を止める（送信の Wi-Fi・HTTPS にメモリを空けるため）。
#pragma once
#include <Arduino.h>

#include "freertos/ringbuf.h"

// ecu.csv 用のリングバッファ。startLogging() が作り、finishSession() が消す（ECU を読まない走行では nullptr）
extern RingbufHandle_t ringEcu;
// ECU のタスクが止まった（記録を閉じるときに待つ）
extern volatile bool ecuStopped;
// つながっているか・読めた数・読めなかった数（シリアルの STATUS に出す）
extern volatile bool ecuConnected;
extern volatile uint32_t ecuReads, ecuErrors;

// "AA:BB:CC:12:22:33" を 6 バイトにする。形が違えば false
bool parseBtAddress(const String &text, uint8_t out[6]);

// ECU のタスクを始める（core 1）。アドレスが読めなければ始めずに false
bool startEcuTask(const String &address);
