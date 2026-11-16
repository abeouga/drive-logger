// ELM327 互換アダプターとのやりとりのうち、Bluetooth に頼らない部分（PC でテストできる。../tests/host/）。
//   - 送ってよい命令かの判定（docs/analysis_policy.md 1.3：読み出しとアダプターへの設定だけ）
//   - 返事（例 "41 0C 1A A8"）からの値の取り出しと、単位への換算
//   - 読む順番（回転数を 2 回に 1 回、残りでスロットル・負荷・吸気圧・点火時期を順番に、油温・吸気温・電圧は 10 秒に 1 回）
// 項目と単位の正式な定義は contracts/sd/ecu.table.json。
#pragma once
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace elm {

// 送ってよい命令か。AT コマンド（アダプター自身への設定）と、モード 01（現在の値）・03（故障コード）の読み出しだけ。
// 故障コードの消去（04）と、送り先や受け取る相手を変える命令などは送らない（docs/analysis_policy.md 1.3）
inline bool allowedCommand(const char *cmd) {
  char c[24];
  size_t n = 0;
  for (const char *p = cmd; *p && n < sizeof(c) - 1; p++) {
    if (*p != ' ') c[n++] = (char)std::toupper((unsigned char)*p);
  }
  c[n] = '\0';
  static const char *const FORBIDDEN[] = {"ATSH", "ATCRA", "ATWM", "ATSW", "ATPP", "ATPB", "ATMA", "ATBD", "04"};
  for (const char *f : FORBIDDEN) {
    if (std::strncmp(c, f, std::strlen(f)) == 0) return false;
  }
  return std::strncmp(c, "AT", 2) == 0 || std::strncmp(c, "01", 2) == 0 || std::strncmp(c, "03", 2) == 0;
}

// 返事から「41 <pid>」に続くデータのバイトを取り出す。見つからなければ -1、見つかればバイト数
inline int replyBytes(const char *reply, const char *pid, uint8_t *out, int maxn) {
  char key[8];
  std::snprintf(key, sizeof(key), "41 %s", pid);
  const char *at = std::strstr(reply, key);
  if (!at) return -1;
  const char *p = at + std::strlen(key);
  int n = 0;
  while (n < maxn) {
    while (*p == ' ') p++;
    if (!std::isxdigit((unsigned char)p[0]) || !std::isxdigit((unsigned char)p[1])) break;
    if (p[2] != '\0' && p[2] != ' ' && p[2] != '\r' && p[2] != '\n') break;
    char h[3] = {p[0], p[1], '\0'};
    out[n++] = (uint8_t)std::strtol(h, nullptr, 16);
    p += 2;
  }
  return n;
}

// pid のバイトを単位に直す（contracts/sd/ecu.table.json）。直せなければ false
inline bool decode(const char *pid, const uint8_t *b, int n, float *value) {
  if (n < 1) return false;
  const int a = b[0];
  if (!std::strcmp(pid, "0C")) {  // 回転数 rpm
    if (n < 2) return false;
    *value = (a * 256 + b[1]) / 4.0f;
  } else if (!std::strcmp(pid, "11") || !std::strcmp(pid, "04")) {  // スロットル開度・負荷 %
    *value = a * 100.0f / 255.0f;
  } else if (!std::strcmp(pid, "0B")) {  // 吸気圧 kPa
    *value = (float)a;
  } else if (!std::strcmp(pid, "0E")) {  // 点火時期 度（上死点前が正）
    *value = a / 2.0f - 64.0f;
  } else if (!std::strcmp(pid, "5C") || !std::strcmp(pid, "0F")) {  // 油温・吸気温 ℃
    *value = a - 40.0f;
  } else if (!std::strcmp(pid, "42")) {  // ECU の電圧 V
    if (n < 2) return false;
    *value = (a * 256 + b[1]) / 1000.0f;
  } else {
    return false;
  }
  return true;
}

// 読む順番。next() が次に送る命令（末尾の 1 は「返事を 1 つ受けたらすぐ戻る」の指定）と pid を返す
struct Item {
  const char *cmd;
  const char *pid;
};

struct Schedule {
  static constexpr uint32_t SLOW_MS = 10000;  // 油温・吸気温・電圧を読む間隔
  uint32_t slot = 0, fastIndex = 0, slowPending = 0;
  bool started = false;
  uint32_t lastSlowMs = 0;

  Item next(uint32_t nowMs) {
    static const Item RPM = {"010C1", "0C"};
    static const Item FAST[] = {{"01111", "11"}, {"01041", "04"}, {"010B1", "0B"}, {"010E1", "0E"}};
    static const Item SLOW[] = {{"015C1", "5C"}, {"010F1", "0F"}, {"01421", "42"}};
    if (!started || nowMs - lastSlowMs >= SLOW_MS) {
      started = true;
      lastSlowMs = nowMs;
      slowPending = 3;
    }
    if (slot++ % 2 == 0) return RPM;
    if (slowPending > 0) return SLOW[3 - slowPending--];
    return FAST[fastIndex++ % 4];
  }
};

}  // namespace elm
