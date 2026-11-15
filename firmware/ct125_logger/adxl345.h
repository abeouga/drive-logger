// ADXL345（I2C 0x53）のレジスタの読み書き、I2C の線の解放、初期化（±16g・ODR は ACCEL_HZ・FIFO ストリーム）
#pragma once
#include <Arduino.h>

bool readRegs(uint8_t reg, uint8_t *buf, uint8_t n);
bool writeReg(uint8_t reg, uint8_t v);

// ESPだけがリセットされたとき、ADXL がつかんだままの SDA を解放する
void i2cBusRecover();

// DEVID を確かめ（5 回まで再試行し events.csv に残す）、測定を始める。DEVID が合わなければ false
bool adxlInit();

// ADXL345 がつながっているか（DEVID を 1 回読むだけ。出来事は残さない。抜き差しを見るため）
bool adxlPresent();

// 外れた ADXL345 の立て直し：I2C の線を解放して開き直し、いれば設定し直して測定を始める。いなければ false
// （つなぎ直した直後の ADXL345 は設定が消えて止まっているので、設定し直す必要がある）
bool adxlReinit();
