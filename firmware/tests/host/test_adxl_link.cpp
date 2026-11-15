// adxl_link.h のテスト（PC で動かす）。CI（.github/workflows/firmware.yml）が g++ でコンパイルして流す。
//   g++ -std=c++17 -I firmware/ct125_logger firmware/tests/host/test_adxl_link.cpp -o /tmp/t && /tmp/t
#include <cstdio>

#include "adxl_link.h"

static int failures = 0;

static void expect(bool ok, const char *what) {
  if (!ok) {
    std::printf("NG: %s\n", what);
    failures++;
  }
}

static void lostAfterStreak() {
  AdxlLink l;
  for (uint32_t i = 1; i < ADXL_LOST_AFTER_ERRORS; i++)
    expect(adxlReadFailed(l, 1000) == AdxlStep::CountError, "続けて失敗しても、決めた回数の手前までは外れたとみなさない");
  expect(!l.lost, "決めた回数の手前では lost にならない");
  expect(adxlReadFailed(l, 1234) == AdxlStep::BecameLost, "決めた回数で外れたとみなす");
  expect(l.lost && l.lostAtMs == 1234, "外れた時刻を覚える");
  expect(adxlReadFailed(l, 1300) == AdxlStep::AlreadyLost, "外れている間の失敗は数えない");
}

static void successResetsStreak() {
  AdxlLink l;
  for (uint32_t i = 1; i < ADXL_LOST_AFTER_ERRORS; i++) adxlReadFailed(l, 0);
  adxlReadOk(l);
  expect(l.streak == 0, "1 回でも読めたら、続いた失敗の数は 0 に戻る");
  expect(adxlReadFailed(l, 0) == AdxlStep::CountError, "途中で読めたら、また最初から数える（一瞬の失敗では外れたとみなさない）");
}

static void retryEverySecond() {
  AdxlLink l;
  for (uint32_t i = 0; i < ADXL_LOST_AFTER_ERRORS; i++) adxlReadFailed(l, 5000);
  expect(!adxlShouldTry(l, 5000 + ADXL_RETRY_MS - 1), "外れた直後は、すぐには試さない");
  expect(adxlShouldTry(l, 5000 + ADXL_RETRY_MS), "決めた間隔がたったら試す");
  expect(!adxlTried(l, 6000, false), "立て直せなかったら false");
  expect(l.lost && l.tries == 1, "立て直せなければ外れたまま。試した回数を数える");
  expect(!adxlShouldTry(l, 6500), "試した後は、また間隔をあける");
  expect(adxlLostMs(l, 7000) == 2000, "外れてからの時間");
  expect(adxlTried(l, 7000, true), "戻ったら true");
  expect(!l.lost && l.streak == 0, "戻ったら lost を外し、失敗の数も 0 に");
  expect(!adxlShouldTry(l, 99999), "戻った後は試さない");
  expect(adxlLostMs(l, 99999) == 0, "戻った後は外れてからの時間は 0");
}

static void millisWrap() {
  AdxlLink l;
  uint32_t near = 0xFFFFFF00u;
  for (uint32_t i = 0; i < ADXL_LOST_AFTER_ERRORS; i++) adxlReadFailed(l, near);
  expect(!adxlShouldTry(l, near + 100), "millis が一周する手前");
  expect(adxlShouldTry(l, near + ADXL_RETRY_MS), "millis が一周しても間隔を正しく測る");
  expect(adxlLostMs(l, near + 5000) == 5000, "millis が一周しても外れてからの時間を正しく測る");
}

static void quiet() {
  expect(quietByVibration(0.01f, false, 0.02f), "ばらつきが小さければ静か");
  expect(!quietByVibration(0.05f, false, 0.02f), "ばらつきが大きければ静かでない");
  expect(!quietByVibration(-1.0f, false, 0.02f), "まだ 1 秒分たまっていなければ静かでない");
  expect(quietByVibration(0.5f, true, 0.02f), "外れている間は、最後のばらつきに関わらず静かとみなす");
}

static void waitUpload() {
  AdxlWait w;
  w.sinceMs = 1000;
  expect(!adxlWaitShouldUpload(w, 1000 + WAIT_ADXL_UPLOAD_MS - 1), "待ち始めてすぐは送らない（走る前につなぐ間を待つ）");
  expect(adxlWaitShouldUpload(w, 1000 + WAIT_ADXL_UPLOAD_MS), "決めた時間待っても来なければ送る");
  w.uploadTried = true;
  expect(!adxlWaitShouldUpload(w, 1000 + 10 * WAIT_ADXL_UPLOAD_MS), "1 回送ろうとしたら、自動では繰り返さない（BOOT ボタンでやり直す）");
}

int main() {
  lostAfterStreak();
  successResetsStreak();
  retryEverySecond();
  millisWrap();
  quiet();
  waitUpload();
  if (failures) {
    std::printf("%d 件失敗\n", failures);
    return 1;
  }
  std::printf("adxl_link: すべて通過\n");
  return 0;
}
