// events.csv への出来事の書き込みと、リングバッファへの追加
#pragma once
#include <Arduino.h>

#include "freertos/ringbuf.h"

// 起動前（SDが開く前）の出来事はここにためて、セッション作成後に書く（openSession() が書く）
extern String pendingEvents;

// リングバッファに 1 行足す。入らなければ ringDrops を数える
void pushTo(RingbufHandle_t r, const char *s, int len);

// "t_us,type,detail" の 1 行をシリアルに出し、events.csv 用のリングバッファ（記録前は pendingEvents）に足す
void logEvent(const char *type, const char *detail);
