// 版の名前・配線・記録の周期・送信のきっかけのしきい値（ファイルをまたいで使う定数）
#pragma once
#include <Arduino.h>

#define FW_VERSION "CT125_LOGGER_V3.9"

const int PIN_SDA = 21, PIN_SCL = 22;
const int PIN_GPS_RX = 32, PIN_GPS_TX = 33;
const int PIN_PPS = -1;              // PPS をつないだら 34 などにする（-1＝使わない）
const int PIN_LED = 2;
// コアの割り振り（V3.8、#132）
//   core 0：loop()（SD への書き込み・送信）と Bluetooth（コントローラーは core 0 に固定。NimBLE のホストも core 0）
//   core 1：加速度の読み出し（優先度 5）・GPS・ECU を読むタスク・LED
// 加速度の読み出しが core 0 で Bluetooth のコントローラーと同居すると、ECU を読んでいる間、加速度の件数が約 0.5% 減った
// （FIFO はあふれていないのに減る。仕組みは分かっていない）。そのため加速度を core 1 に置き、loop() を core 0 に移す。
// loop() のコアは Arduino の設定で決まるので、FQBN に LoopCore=0 を付けてコンパイルする（README の「書き込み方」）。
#if ARDUINO_RUNNING_CORE != 0
#error "loop() を core 0 で動かす（FQBN に LoopCore=0 を付けてコンパイルする）。#132"
#endif
const BaseType_t ACCEL_CORE = 1;
// SD に書いている間の loop() の優先度（V3.8、#132）。SD の書き込みは途中で割り込まれると失敗する
// （core 0 では Bluetooth のコントローラーの優先度 23 に割り込まれる）ので、書いている間だけ一番上（24）に上げる。
// この間（最長 約 140 ms）、core 0 の Bluetooth の処理は待たされるが、BLE が切れると判断されるのは 2 秒なので切れない。
const UBaseType_t SD_WRITE_PRIORITY = configMAX_PRIORITIES - 1;
const int PIN_BOOT = 0;              // 開発ボードの BOOT ボタン（押すと LOW）。起動後は普通の入力として使える
const uint32_t GPS_BAUD = 9600;
const int PIN_SD_CS = 5;
const uint32_t SD_HZ = 4000000;
const uint8_t ADXL = 0x53;
const float G_PER_LSB = 0.0039f;     // フル分解能
// ADXL345 の ODR。I2C 400 kHz で使う。0x0C＝400 Hz、0x0D＝800 Hz（帯域はそれぞれ半分）。V3.4 までは 400 Hz
const uint8_t ADXL_BW_RATE = 0x0D;
const float ACCEL_HZ = 800.0f;       // ADXL_BW_RATE と合わせる
const uint32_t FLUSH_MS = 1000;
const uint32_t STATUS_MS = 10000;

// 送信のきっかけ（docs/device_upload_design.md の「3.1 いつ送るか」）
const float QUIET_STD_G = 0.02f;        // 1 秒間の合成加速度のばらつきがこれ未満なら「静か」（エンジン停止。静止時の雑音は約 0.008g）
const float MOVING_STD_G = 0.05f;       // これを超えたら「動いている」（アイドリングや走行）
const float STOP_SPEED_KMH = 5.0f;      // GPS 速度がこれ未満なら止まっている（contracts/common.json。止まっていても 0〜4 km/h 出る）
const uint32_t QUIET_SECONDS = 120;     // 静かな状態がこれだけ続いたら記録を閉じて送る
const uint32_t BUTTON_HOLD_MS = 2000;   // BOOT ボタンをこれだけ押し続けたら、今すぐ送る
const uint32_t MOVING_SECONDS_TO_WAKE = 3;  // 待機中、これだけ続けて動いたら再起動して記録を始める
