// ADXL345（I2C 0x53）のレジスタの読み書き、I2C の線の解放、初期化（±16g・400Hz・FIFO ストリーム）
#pragma once
#include <Arduino.h>

bool readRegs(uint8_t reg, uint8_t *buf, uint8_t n);
bool writeReg(uint8_t reg, uint8_t v);

// ESPだけがリセットされたとき、ADXL がつかんだままの SDA を解放する
void i2cBusRecover();

// DEVID を確かめ（5 回まで再試行し events.csv に残す）、測定を始める。DEVID が合わなければ false
bool adxlInit();
