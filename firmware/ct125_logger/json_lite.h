#pragma once
// 小さな JSON の読み取り（送信の手順の応答・meta.json・upload_state.json）。ライブラリを使わず、フラッシュを増やさない。
// Arduino の String だけに頼るので、PC でもテストできる（firmware/tests/host/）。
#include <Arduino.h>
#include <ctype.h>
#include <string.h>

namespace jsonlite {

// 送る走行の判定（contracts/upload/upload.json の device_rules）：meta.json の "firmware" の値が
// CT125_LOGGER_V<版> で、版の上の数が MIN_UPLOADABLE_MAJOR 以上（それより前の走行は PC から上げ済み・机上の試験）
const char *const FIRMWARE_NAME = "CT125_LOGGER_V";
const int MIN_UPLOADABLE_MAJOR = 3;

// JSON の文字列の値を取り出す："key" の後に（空白を挟んでよい）コロン、（空白を挟んでよい）"値"。
// 値の中のエスケープ（\" \/ \\）は 1 文字に戻す。キーが無い・値が文字列でなければ空文字。
// from から探し、end を渡すと値の終わりの " の位置を返す（配列の中を順に読むとき）
inline String jsonString(const String &json, const char *key, int from = 0, int *end = nullptr) {
  const String quotedKey = String("\"") + key + "\"";
  const int n = json.length();
  for (int k = json.indexOf(quotedKey, from); k >= 0; k = json.indexOf(quotedKey, k + 1)) {
    int i = k + quotedKey.length();
    while (i < n && isspace((unsigned char)json[i])) i++;
    if (i >= n || json[i] != ':') continue;  // キーではなく、値の中に同じ文字列があった
    i++;
    while (i < n && isspace((unsigned char)json[i])) i++;
    if (i >= n || json[i] != '"') return "";
    String value;
    for (int j = i + 1; j < n; j++) {
      char c = json[j];
      if (c == '\\' && j + 1 < n) {
        value += json[++j];
        continue;
      }
      if (c == '"') {
        if (end) *end = j;
        return value;
      }
      value += c;
    }
    return "";
  }
  return "";
}

inline bool isUploadableFirmware(const String &meta) {
  String firmware = jsonString(meta, "firmware");
  if (!firmware.startsWith(FIRMWARE_NAME)) return false;
  String version = firmware.substring(strlen(FIRMWARE_NAME));
  if (version.length() == 0 || !isdigit((unsigned char)version[0])) return false;
  return version.toInt() >= MIN_UPLOADABLE_MAJOR;
}

}  // namespace jsonlite
