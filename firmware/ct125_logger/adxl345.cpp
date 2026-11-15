#include "adxl345.h"

#include <Wire.h>

#include "event_log.h"
#include "logger_constants.h"

bool readRegs(uint8_t reg, uint8_t *buf, uint8_t n) {
  Wire.beginTransmission(ADXL);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ADXL, n) != n) return false;
  for (int i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

bool writeReg(uint8_t reg, uint8_t v) {
  Wire.beginTransmission(ADXL);
  Wire.write(reg);
  Wire.write(v);
  return Wire.endTransmission() == 0;
}

// ESPだけがリセットされると、ADXLが読み出しの途中でSDAをLOWにつかんだまま残ることがある。
// SCLを最大9回動かしてADXLに残りのビットを吐き出させ、STOPを送って線を解放する。
void i2cBusRecover() {
  pinMode(PIN_SDA, INPUT_PULLUP);
  pinMode(PIN_SCL, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_SCL, HIGH);
  delayMicroseconds(10);
  for (int i = 0; i < 9 && digitalRead(PIN_SDA) == LOW; i++) {
    digitalWrite(PIN_SCL, LOW);
    delayMicroseconds(10);
    digitalWrite(PIN_SCL, HIGH);
    delayMicroseconds(10);
  }
  pinMode(PIN_SDA, OUTPUT_OPEN_DRAIN);   // STOP: SCL=HIGH のまま SDA を LOW→HIGH
  digitalWrite(PIN_SDA, LOW);
  delayMicroseconds(10);
  digitalWrite(PIN_SDA, HIGH);
  delayMicroseconds(10);
  pinMode(PIN_SDA, INPUT);
  pinMode(PIN_SCL, INPUT);
}

bool adxlInit() {
  uint8_t id = 0;
  for (int attempt = 1; attempt <= 5; attempt++) {
    id = 0;
    if (readRegs(0x00, &id, 1) && id == 0xE5) break;
    char d[32];
    snprintf(d, sizeof(d), "attempt=%d devid=0x%02X", attempt, id);
    logEvent("adxl_retry", d);
    Wire.end();
    i2cBusRecover();
    Wire.begin(PIN_SDA, PIN_SCL, 400000);
    delay(20);
  }
  if (id != 0xE5) return false;
  writeReg(0x2D, 0x00);        // 設定中は停止
  writeReg(0x31, 0x0B);        // DATA_FORMAT: FULL_RES, ±16g
  writeReg(0x2C, ADXL_BW_RATE); // BW_RATE: ODR（logger_constants.h）
  writeReg(0x38, 0x00);        // FIFO を空にする（バイパス）
  writeReg(0x38, 0x80 | 16);   // FIFO_CTL: ストリームモード
  writeReg(0x2D, 0x08);        // POWER_CTL: 測定開始
  return true;
}
