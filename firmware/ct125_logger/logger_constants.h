// 版の名前・配線・記録の周期・送信のきっかけのしきい値（ファイルをまたいで使う定数）
#pragma once
#include <Arduino.h>

#define FW_VERSION "CT125_LOGGER_V3.3"

const int PIN_SDA = 21, PIN_SCL = 22;
const int PIN_GPS_RX = 32, PIN_GPS_TX = 33;
const int PIN_PPS = -1;              // PPS をつないだら 34 などにする（-1＝使わない）
const int PIN_LED = 2;
const int PIN_BOOT = 0;              // 開発ボードの BOOT ボタン（押すと LOW）。起動後は普通の入力として使える
const uint32_t GPS_BAUD = 9600;
const int PIN_SD_CS = 5;
const uint32_t SD_HZ = 4000000;
const uint8_t ADXL = 0x53;
const float G_PER_LSB = 0.0039f;     // フル分解能
const float ACCEL_HZ = 400.0f;       // BW_RATE=0x0C
const uint32_t FLUSH_MS = 1000;
const uint32_t STATUS_MS = 10000;

// 送信のきっかけ（設計書 3.1）
const float QUIET_STD_G = 0.02f;        // 1 秒間の合成加速度のばらつきがこれ未満なら「静か」（エンジン停止。静止時の雑音は約 0.008g）
const float MOVING_STD_G = 0.05f;       // これを超えたら「動いている」（アイドリングや走行）
const float STOP_SPEED_KMH = 5.0f;      // GPS 速度がこれ未満なら止まっている（contracts/common.json。止まっていても 0〜4 km/h 出る）
const uint32_t QUIET_SECONDS = 120;     // 静かな状態がこれだけ続いたら記録を閉じて送る
const uint32_t BUTTON_HOLD_MS = 2000;   // BOOT ボタンをこれだけ押し続けたら、今すぐ送る
const uint32_t MOVING_SECONDS_TO_WAKE = 3;  // 待機中、これだけ続けて動いたら再起動して記録を始める
