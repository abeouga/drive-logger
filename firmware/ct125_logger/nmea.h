// NMEA 文の読み取り（欄の取り出し・緯度経度の度への変換・チェックサム）
#pragma once
#include <Arduino.h>

// 0 から数えて n 番目の欄（'*' の前まで）。無ければ空
String nmeaField(const String &s, int n);

// "ddmm.mmmm" と N/S/E/W から、南・西を負にした度（小数 7 桁）。短すぎれば空
String nmeaDeg(const String &v, const String &hemi);

// "$...*hh" のチェックサムが合うか
bool nmeaChecksumOk(const String &s);
