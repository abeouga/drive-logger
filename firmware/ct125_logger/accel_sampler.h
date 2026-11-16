// 加速度のサンプリング（コア0）：ADXL345 の FIFO を読み、時刻を補正して（PLL）accel.csv の行をリングバッファに入れる
#pragma once
#include <Arduino.h>

// status.csv に書く、時刻のなめらかさの値（dt_min/dt_max/pll_err_max は writeStatus() が 10 秒ごとに戻す）
extern volatile double pllPeriodUs;
extern volatile int32_t statDtMin, statDtMax, statErrMax;
extern volatile uint32_t timeResyncs;
// 診断（#132）：この 10 秒の、FIFO にたまっていた件数の最大・FIFO を見に行く間隔の最大・まとめて読むのにかかった時間の最大
extern volatile int32_t statFifoMax, statPollGapMax, statBatchUsMax;

// 直近 1 秒の合成加速度の標準偏差 [g]（まだ無ければ -1）。送信のきっかけの判定に使う
extern volatile float accelStd1s;

// stopRequested が立つまで回る（xTaskCreatePinnedToCore に渡す）
void sensorTask(void *);
