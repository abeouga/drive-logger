// elm_parse.h のテスト（PC で動かす）。CI（.github/workflows/firmware.yml）が g++ でコンパイルして流す。
//   g++ -std=c++17 -I firmware/tests/host -I firmware/ct125_logger firmware/tests/host/test_elm_parse.cpp -o /tmp/t && /tmp/t
// 返事の例は #127 で CT125（JA55）の ECU から実際に返ってきたもの。
#include <cmath>
#include <cstdio>
#include <cstring>

#include "elm_parse.h"

static int failures = 0;

static void expect(bool ok, const char *what) {
  if (!ok) {
    std::printf("NG: %s\n", what);
    failures++;
  }
}

static bool near(float a, float b) { return std::fabs(a - b) < 0.01f; }

static bool decodeReply(const char *reply, const char *pid, float *value) {
  uint8_t b[4];
  int n = elm::replyBytes(reply, pid, b, 4);
  return n > 0 && elm::decode(pid, b, n, value);
}

int main() {
  // 送ってよい命令（docs/analysis_policy.md 1.3）
  expect(elm::allowedCommand("ATZ"), "ATZ は送る");
  expect(elm::allowedCommand("ATSP5"), "ATSP5 は送る");
  expect(elm::allowedCommand("010C1"), "010C1 は送る");
  expect(elm::allowedCommand("01 0C"), "空白の入ったモード 01 も送る");
  expect(elm::allowedCommand("03"), "故障コードの読み出しは送る");
  expect(elm::allowedCommand("atrv"), "小文字の AT も送る");
  expect(!elm::allowedCommand("04"), "故障コードの消去は送らない");
  expect(!elm::allowedCommand("0 4"), "空白で区切った消去も送らない");
  expect(!elm::allowedCommand("ATSH 72 05 71"), "送り先の書き換えは送らない");
  expect(!elm::allowedCommand("atcra 7E8"), "受け取る相手の書き換えは送らない");
  expect(!elm::allowedCommand("ATWM 81 10 F1 3E"), "キープアライブの書き換えは送らない");
  expect(!elm::allowedCommand("ATMA"), "バスの全部を受け続ける命令は送らない");
  expect(!elm::allowedCommand("0902"), "モード 09 は送らない");
  expect(!elm::allowedCommand("2E0101"), "書き込みの要求は送らない");
  expect(!elm::allowedCommand("72 05 71 11"), "メーカー独自の要求は送らない");
  expect(!elm::allowedCommand(""), "空は送らない");

  // 返事の読み取りと換算（#127 の実際の返事）
  float v = 0;
  expect(decodeReply("41 0C 1A A8", "0C", &v) && near(v, 1706.0f), "回転数 1A A8 → 1706 rpm");
  expect(decodeReply("41 0C 3E B4", "0C", &v) && near(v, 4013.0f), "回転数 3E B4 → 4013 rpm");
  expect(decodeReply("41 0C 00 00", "0C", &v) && near(v, 0.0f), "回転数 0");
  expect(decodeReply("41 11 19", "11", &v) && near(v, 9.80f), "スロットル開度 19 → 9.8 %");
  expect(decodeReply("41 04 00", "04", &v) && near(v, 0.0f), "負荷 0 %");
  expect(decodeReply("41 0B 65", "0B", &v) && near(v, 101.0f), "吸気圧 65 → 101 kPa");
  expect(decodeReply("41 0E 80", "0E", &v) && near(v, 0.0f), "点火時期 80 → 0 度");
  expect(decodeReply("41 0F 3D", "0F", &v) && near(v, 21.0f), "吸気温 3D → 21 ℃");
  expect(decodeReply("41 5C 3D", "5C", &v) && near(v, 21.0f), "油温 3D → 21 ℃");
  expect(decodeReply("41 42 2D 50", "42", &v) && near(v, 11.6f), "ECU の電圧 2D 50 → 11.6 V");
  expect(decodeReply("SEARCHING... 41 0C 1A A8", "0C", &v) && near(v, 1706.0f), "前置きがあっても読む");

  // 読めない返事
  expect(!decodeReply("NO DATA", "0C", &v), "NO DATA は読めない");
  expect(!decodeReply("TIMEOUT", "0C", &v), "時間切れは読めない");
  expect(!decodeReply("41 0C 1A", "0C", &v), "回転数の 2 バイト目が無ければ読めない");
  expect(!decodeReply("7F 01 12", "0C", &v), "断りの返事は読めない");
  expect(!decodeReply("41 11 19", "0C", &v), "違う項目の返事は読めない");
  expect(!decodeReply("41 0C 1AA8", "0C", &v), "区切られていない 16 進は読めない");

  // 読む順番：回転数を 2 回に 1 回。最初の 10 秒の頭で油温・吸気温・電圧を 1 回ずつ
  elm::Schedule s;
  const char *expected[] = {"0C", "5C", "0C", "0F", "0C", "42", "0C", "11", "0C", "04", "0C", "0B", "0C", "0E", "0C", "11"};
  bool order = true;
  for (const char *pid : expected) {
    elm::Item item = s.next(1000);
    if (std::strcmp(item.pid, pid) != 0) order = false;
  }
  expect(order, "読む順番（回転数を 2 回に 1 回、遅い項目は 10 秒の頭に）");
  elm::Item rpm = s.next(5000);
  elm::Item afterFiveSec = s.next(5000);
  expect(!std::strcmp(rpm.pid, "0C") && std::strcmp(afterFiveSec.pid, "5C") != 0, "10 秒たつまでは遅い項目を読まない");
  s.next(11001);  // 回転数
  elm::Item slow = s.next(11001);
  expect(!std::strcmp(slow.pid, "5C"), "10 秒たったら遅い項目をまた読む");
  bool allAllowed = true;
  elm::Schedule t;
  for (int i = 0; i < 40; i++) {
    if (!elm::allowedCommand(t.next(static_cast<uint32_t>(i) * 200).cmd)) allAllowed = false;
  }
  expect(allAllowed, "読む順番の命令は、すべて送ってよい命令");

  if (failures) {
    std::printf("%d 件 NG\n", failures);
    return 1;
  }
  std::printf("OK\n");
  return 0;
}
