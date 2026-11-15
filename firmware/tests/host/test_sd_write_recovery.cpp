// sd_write_recovery.h のテスト（PC で動かす）。CI（.github/workflows/firmware.yml）が g++ でコンパイルして流す。
//   g++ -std=c++17 -I firmware/ct125_logger firmware/tests/host/test_sd_write_recovery.cpp -o /tmp/t && /tmp/t
//
// FakeSink は FatFs のふるまいをまねる：書き込みに 1 度失敗すると、開き直すまで以後の書き込みをすべて断る。
// 失敗したときに手元にあった分（書けたことにした分を含む）は SD に残らない。
#include <cstdio>
#include <string>
#include <vector>

#include "sd_write_recovery.h"

static int failures = 0;

static void expect(bool ok, const char *what) {
  if (!ok) {
    std::printf("NG: %s\n", what);
    failures++;
  }
}

struct FakeSink {
  std::string disk;                // SD に残った中身
  bool sticky = false;             // FatFs のファイルのエラー（開き直すまで消えない）
  long failAfter = -1;             // あと何バイト書いたら失敗するか（-1＝失敗しない）
  int reopenFailures = 0;          // 開き直しがこの回数だけ失敗する
  int reopens = 0;
  bool failAgainAfterReopen = false;  // 開き直した直後の書き込みも失敗させる
  std::vector<std::string> events;

  size_t write(const char *d, size_t n) {
    if (sticky) return 0;
    if (failAfter >= 0 && (long)n > failAfter) {
      size_t ok = (size_t)failAfter;  // ここまでは書けた（とライブラリは返す）が、SD には残らない
      failAfter = -1;
      sticky = true;
      return ok;
    }
    if (failAfter >= 0) failAfter -= (long)n;
    disk.append(d, n);
    return n;
  }
  bool reopen() {
    reopens++;
    if (reopenFailures > 0) {
      reopenFailures--;
      return false;
    }
    sticky = false;
    if (failAgainAfterReopen) failAfter = 0;
    return true;
  }
  const char *name() const { return "accel.csv"; }
  void logEvent(const char *type, const char *detail) { events.push_back(std::string(type) + " " + detail); }
};

static SdWriteResult put(FakeSink &s, SdFileGuard &g, const std::string &d, uint32_t now) {
  return sdWriteChunk(s, g, d.data(), d.size(), now);
}

int main() {
  {  // ふだん：そのまま書く
    FakeSink s;
    SdFileGuard g;
    SdWriteResult r = put(s, g, "0,10,1,2,3\n1,20,1,2,3\n", 0);
    expect(s.disk == "0,10,1,2,3\n1,20,1,2,3\n", "ふだんはそのまま書く");
    expect(r.errors == 0 && r.written == 22, "ふだんはエラー 0・全部書けた");
    expect(s.events.empty(), "ふだんは出来事なし");
  }
  {  // 書き込みの途中で失敗 → その場で開き直し、切れた行を閉じて次の行の頭から書く
    FakeSink s;
    SdFileGuard g;
    put(s, g, "0,10,1,2,3\n", 0);
    s.failAfter = 4;  // 次のかたまりの 4 バイト目で失敗
    SdWriteResult r = put(s, g, "1,20,1,2,3\n2,30,1,2,3\n3,40,1,2,3\n", 100);
    expect(r.errors == 1, "失敗は 1 回と数える");
    expect(s.reopens == 1 && !g.broken, "その場で開き直せた");
    expect(s.disk == "0,10,1,2,3\n\n2,30,1,2,3\n3,40,1,2,3\n", "切れた行の残りを捨て、次の行の頭から書く");
    expect(s.events.size() == 2 && s.events[0] == "sd_write_error file=accel.csv" &&
               s.events[1] == "sd_reopen file=accel.csv tries=1",
           "events に sd_write_error と sd_reopen を残す");
    put(s, g, "4,50,1,2,3\n", 200);
    expect(s.disk.substr(s.disk.size() - 11) == "4,50,1,2,3\n", "開き直したあとも書き続ける");
  }
  {  // 開き直せない間は書かず、SD_REOPEN_RETRY_MS ごとに試す。開けたら、かたまりの途中からでも行の頭から書く
    FakeSink s;
    SdFileGuard g;
    s.failAfter = 0;
    s.reopenFailures = 2;
    SdWriteResult r = put(s, g, "0,10,1,2,3\n", 1000);
    expect(r.errors == 1 && g.broken, "開き直せなければ broken");
    expect(!sdEnsureWritable(s, g, 1000 + SD_REOPEN_RETRY_MS - 1), "間を置くまでは試さない");
    expect(s.reopens == 1, "試していない");
    expect(!sdEnsureWritable(s, g, 1000 + SD_REOPEN_RETRY_MS), "2 回目も開けない");
    expect(sdEnsureWritable(s, g, 1000 + 2 * SD_REOPEN_RETRY_MS), "3 回目で開けた");
    expect(s.events.back() == "sd_reopen file=accel.csv tries=3", "試した回数を残す");
    put(s, g, ",2,3\n5,60,1,2,3\n", 4000);  // 行の途中から始まるかたまり
    expect(s.disk == "\n5,60,1,2,3\n", "かたまりの途中の行は捨てる");
  }
  {  // 行の頭が来ないかたまりは丸ごと捨て、次のかたまりで探す
    FakeSink s;
    SdFileGuard g;
    g.needSeam = true;
    put(s, g, "0.123", 0);
    expect(s.disk.empty() && g.needSeam, "改行が無ければまだ書かない");
    put(s, g, "4\n7,1,1,1,1\n", 0);
    expect(s.disk == "\n7,1,1,1,1\n", "次のかたまりで行の頭から書く");
  }
  {  // 開き直してもまたすぐ書けない：その回は諦めて broken にする（同じかたまりで何度も試さない）
    FakeSink s;
    SdFileGuard g;
    put(s, g, "0,10,1,2,3\n", 0);
    s.failAfter = 2;
    s.failAgainAfterReopen = true;
    SdWriteResult r = put(s, g, "1,20,1,2,3\n2,30,1,2,3\n", 50);
    expect(r.errors == 2 && g.broken && s.reopens == 1, "開き直しはその場で 1 度だけ");
    expect(s.events.size() == 2, "sd_write_error は 1 つのかたまりで 1 度だけ");
  }
  expect(nextLineStart("ab\ncd", 0, 5) == 3 && nextLineStart("abc", 0, 3) == 3, "nextLineStart");

  if (failures) {
    std::printf("%d 件 NG\n", failures);
    return 1;
  }
  std::printf("OK\n");
  return 0;
}
