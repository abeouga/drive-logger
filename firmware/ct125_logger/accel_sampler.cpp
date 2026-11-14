#include "accel_sampler.h"

#include <math.h>

#include "adxl345.h"
#include "event_log.h"
#include "logger_constants.h"
#include "logger_state.h"

volatile float accelStd1s = -1;

// 時刻の付け方
//   FIFO を読んだ瞬間の時刻を付けると、ESP が FIFO を見に行く間隔（約1ms）で時刻が丸められ、
//   間隔が 2ms／3ms に割れる。
//   そこで「前のサンプルの時刻＋周期」で時刻を進め、読んだ時刻とのずれ（err）は
//   少しずつだけ時刻と周期に戻す（PLL）。間隔はなめらかになり、長時間でも ESP の時計からずれない。
//   ずれが 20ms を超えたら（長い停止のあとなど）、合わせ直して events.csv に time_resync を残す。
const double PLL_KP = 0.02;     // 時刻の補正の強さ
const double PLL_KF = 0.0001;   // 周期の補正の強さ
const double RESYNC_US = 20000;
volatile double pllPeriodUs = 1e6 / ACCEL_HZ;
volatile int32_t statDtMin = INT32_MAX, statDtMax = 0, statErrMax = 0;
volatile uint32_t timeResyncs = 0;

void sensorTask(void *) {
  char buf[64 * 33];
  uint8_t raw[6];
  double periodUs = 1e6 / ACCEL_HZ;   // 実測に合わせて PLL が更新する
  double tNext = -1;                  // 次のサンプルに付ける時刻
  int64_t tPrev = -1;
  // 設定から記録開始までの間に FIFO があふれているので、空にしてから始める
  writeReg(0x38, 0x00);
  writeReg(0x38, 0x80 | 16);
  uint8_t clr;
  readRegs(0x30, &clr, 1);
  // 1 秒ごとの合成加速度のばらつき（送信のきっかけの判定用）
  double magSum = 0, magSumSq = 0;
  int magCount = 0;
  for (;;) {
    if (stopRequested) {
      accelStopped = true;
      vTaskDelete(nullptr);
    }
    uint8_t st = 0, src = 0;
    if (!readRegs(0x39, &st, 1) || !readRegs(0x30, &src, 1)) {
      i2cErrors++;
      vTaskDelay(1);
      continue;
    }
    if ((src & 0x01) && samples > 0) {   // 記録開始前（n=0）のあふれは記録の欠けではないので数えない
      fifoOverruns++;
      char d[24];
      snprintf(d, sizeof(d), "n=%lu", (unsigned long)samples);
      logEvent("fifo_overrun", d);
    }
    int n = st & 0x3F;
    if (n < 4) {                      // 数件たまってからまとめて読む（FIFO は32件＝約80ms分あるので余裕あり）
      vTaskDelay(2);
      continue;
    }
    int64_t now = nowUs();
    // いちばん新しいサンプルは、読んだ時刻の「0〜1周期前」にできている → 平均して半周期前とみなす
    double expectedLast = now - periodUs * 0.5;
    if (tNext < 0) tNext = expectedLast - (n - 1) * periodUs;
    double err = expectedLast - (tNext + (n - 1) * periodUs);
    if (fabs(err) > RESYNC_US) {
      char d[40];
      snprintf(d, sizeof(d), "err_us=%.0f n=%lu", err, (unsigned long)samples);
      logEvent("time_resync", d);
      timeResyncs++;
      tNext = expectedLast - (n - 1) * periodUs;
      err = 0;
    } else {
      tNext += PLL_KP * err;
      periodUs += PLL_KF * err;
    }
    if (fabs(err) > statErrMax) statErrMax = (int32_t)fabs(err);
    int len = 0, got = 0;
    for (int i = 0; i < n; i++) {
      if (!readRegs(0x32, raw, 6)) {
        i2cErrors++;
        break;
      }
      int16_t x = raw[0] | (raw[1] << 8), y = raw[2] | (raw[3] << 8), z = raw[4] | (raw[5] << 8);
      int64_t tUs = (int64_t)(tNext + i * periodUs);
      if (tPrev >= 0) {
        int32_t dt = (int32_t)(tUs - tPrev);
        if (dt < statDtMin) statDtMin = dt;
        if (dt > statDtMax) statDtMax = dt;
      }
      tPrev = tUs;
      if (firstSampleUs < 0) firstSampleUs = tUs;
      lastSampleUs = tUs;
      float gx = x * G_PER_LSB, gy = y * G_PER_LSB, gz = z * G_PER_LSB;
      len += snprintf(buf + len, sizeof(buf) - len, "%lu,%lld,%.4f,%.4f,%.4f\n", (unsigned long)samples,
                      (long long)tUs, gx, gy, gz);
      samples++;
      got++;
      double mag = sqrt((double)gx * gx + (double)gy * gy + (double)gz * gz);
      magSum += mag;
      magSumSq += mag * mag;
      if (++magCount >= (int)ACCEL_HZ) {
        double mean = magSum / magCount;
        double var = magSumSq / magCount - mean * mean;
        accelStd1s = (float)sqrt(var > 0 ? var : 0);
        if (accelStd1s > MOVING_STD_G) hasMoved = true;
        magSum = magSumSq = 0;
        magCount = 0;
      }
    }
    tNext += got * periodUs;
    pllPeriodUs = periodUs;
    if (len) pushTo(ringAccel, buf, len);
  }
}
