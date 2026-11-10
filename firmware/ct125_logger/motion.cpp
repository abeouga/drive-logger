#include "motion.h"

#include <math.h>

#include "accel_sampler.h"
#include "adxl345.h"
#include "gps_task.h"
#include "logger_constants.h"
#include "logger_state.h"

// ------------------------------------------------------------------ 記録中
static bool isQuietNow() {
  bool stillVibration = accelStd1s >= 0 && accelStd1s < QUIET_STD_G;
  bool stopped = gpsStatus != 'A' || gpsSpeedKmh < STOP_SPEED_KMH;  // 屋内などで GPS が無いときは振動だけで見る
  return stillVibration && stopped;
}

const char *uploadTrigger(uint32_t &quietSeconds) {
  quietSeconds = isQuietNow() ? quietSeconds + 1 : 0;
  if (hasMoved && quietSeconds >= QUIET_SECONDS) return "quiet";
  return nullptr;
}

// ------------------------------------------------------------------ 送信中・待機中
// 記録を止めた後も ADXL345 は測り続けている。FIFO から 40 件読んで、ばらつきで動いているかを見る
bool movingNow() {
  uint8_t raw[6];
  double sum = 0, sumSq = 0;
  int n = 0;
  for (int i = 0; i < 40; i++) {
    if (!readRegs(0x32, raw, 6)) continue;
    int16_t x = raw[0] | (raw[1] << 8), y = raw[2] | (raw[3] << 8), z = raw[4] | (raw[5] << 8);
    double mag = sqrt((double)x * x + (double)y * y + (double)z * z) * G_PER_LSB;
    sum += mag;
    sumSq += mag * mag;
    n++;
    delay(3);
  }
  if (n < 10) return false;
  double mean = sum / n;
  double var = sumSq / n - mean * mean;
  return sqrt(var > 0 ? var : 0) > MOVING_STD_G;
}

bool movingForAWhile() {
  for (int i = 0; i < 3; i++) {
    if (!movingNow()) return false;
    delay(300);
  }
  return true;
}
