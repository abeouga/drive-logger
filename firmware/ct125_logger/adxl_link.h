// ADXL345 の抜き差しの判定（外れたとみなす・立て直しを試す・待っている間に送る）。
//
// 実機では、ADXL345 を ESP32 から外して車両のフレームに付け、走るときに起動後につなぎ、
// 送るときは外して ESP32 だけを Wi-Fi の届く所へ持っていく。そのため ADXL345 は
//   - 起動時に無いことがある（待つ。待っている間に送り残しを送る）
//   - 記録中に外れることがある（読み出しの失敗が続いたら「外れた」とみなし、1 秒ごとに立て直しを試す）
// どちらも I2C の読み出しが失敗するだけで、外れたのか一瞬の失敗かは区別できない。
// ここでは失敗が ADXL_LOST_AFTER_ERRORS 回続いたら外れたとみなす。
//
// I2C や Arduino に頼らないので、PC でテストできる（../tests/host/test_adxl_link.cpp）。
#pragma once
#include <stdint.h>

const uint32_t ADXL_LOST_AFTER_ERRORS = 50;   // 読み出しの失敗がこれだけ続いたら、外れたとみなす
const uint32_t ADXL_RETRY_MS = 1000;          // 外れている間、立て直しを試す間隔
const uint32_t WAIT_ADXL_UPLOAD_MS = 30000;   // 起動時に ADXL345 が無く、これだけ待っても来なければ送り残しを送る

// ------------------------------------------------------------------ 記録中
struct AdxlLink {
  bool lost = false;       // 外れたとみなしている
  uint32_t streak = 0;     // 続けて失敗した回数
  uint32_t lostAtMs = 0;   // 外れたとみなした時刻（millis）
  uint32_t lastTryMs = 0;  // 最後に立て直しを試した時刻
  uint32_t tries = 0;      // 外れてから立て直しを試した回数
};

enum class AdxlStep {
  CountError,  // 失敗を 1 回数える（まだ外れたとはみなさない）
  BecameLost,  // 今、外れたとみなした（events.csv に adxl_lost を残す）
  AlreadyLost, // 外れている間の失敗（数えない。立て直しは adxlShouldTry で）
};

inline void adxlReadOk(AdxlLink &l) { l.streak = 0; }

inline AdxlStep adxlReadFailed(AdxlLink &l, uint32_t nowMs) {
  if (l.lost) return AdxlStep::AlreadyLost;
  if (++l.streak < ADXL_LOST_AFTER_ERRORS) return AdxlStep::CountError;
  l.lost = true;
  l.lostAtMs = nowMs;
  l.lastTryMs = nowMs;
  l.tries = 0;
  return AdxlStep::BecameLost;
}

// 外れている間、立て直しを試す時か（millis が一周しても引き算で正しく測れる）
inline bool adxlShouldTry(const AdxlLink &l, uint32_t nowMs) {
  return l.lost && (uint32_t)(nowMs - l.lastTryMs) >= ADXL_RETRY_MS;
}

// 立て直しを試した結果。戻ったら true を返す（events.csv に adxl_back を残す）
inline bool adxlTried(AdxlLink &l, uint32_t nowMs, bool ok) {
  l.lastTryMs = nowMs;
  l.tries++;
  if (!ok) return false;
  l.lost = false;
  l.streak = 0;
  return true;
}

inline uint32_t adxlLostMs(const AdxlLink &l, uint32_t nowMs) { return l.lost ? (uint32_t)(nowMs - l.lostAtMs) : 0; }

// 「静か」の振動の側。ADXL345 が外れていたら、振動は見られないので静かとみなす
// （外したまま止まって 2 分たったら、走り終わったとみなして記録を閉じ、送るため）
inline bool quietByVibration(float std1s, bool lost, float quietStdG) {
  return lost || (std1s >= 0 && std1s < quietStdG);
}

// ------------------------------------------------------------------ 起動時に無かったとき
struct AdxlWait {
  uint32_t sinceMs = 0;      // 待ち始めた時刻
  bool uploadTried = false;  // この待ちの間に送り残しを送ろうとした
};

inline bool adxlWaitShouldUpload(const AdxlWait &w, uint32_t nowMs) {
  return !w.uploadTried && (uint32_t)(nowMs - w.sinceMs) >= WAIT_ADXL_UPLOAD_MS;
}
