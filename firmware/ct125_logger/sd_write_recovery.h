// SD に書けなくなった CSV の立て直し（開き直して、次の行の頭から書き続ける）。
//
// SD のファイルは FatFs が扱う。FatFs は、1 回でもカードへの書き込みに失敗すると、そのファイルにエラーを覚え
// （FIL の err）、以後の f_write をすべて断る。エラーが消えるのは、ファイルを閉じて開き直したときだけ。
// そのため、カードが一瞬応答しなかっただけでも、開いたままのファイル（accel.csv など）はその後ずっと書けない。
// ここでは、書けなかったらその場で 1 度開き直し、だめなら SD_REOPEN_RETRY_MS ごとに開き直しを試す。
//
// 開き直したあとは、切れた行を改行で閉じ、手元のデータの次の行の頭から書く（CSV の 1 行に 2 つの行が混ざらないように）。
// 切れた行の残りは捨てる。何が起きたかは events.csv の sd_write_error・sd_reopen に残す。
//
// SD や Arduino に頼らないので、PC でテストできる（../tests/host/test_sd_write_recovery.cpp）。
// Sink に要るもの：
//   size_t write(const char *data, size_t n)   書けたバイト数を返す
//   bool reopen()                               閉じて、追記で開き直す。開けたら true
//   const char *name() const                    ファイル名（出来事の detail に書く）
//   void logEvent(const char *type, const char *detail)
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

const uint32_t SD_REOPEN_RETRY_MS = 1000;  // 開き直せなかったとき、次に試すまでの間

// ファイルごとの状態
struct SdFileGuard {
  bool broken = false;     // 書けなくなり、まだ開き直せていない（この間はリングバッファから取り出さない）
  bool needSeam = false;   // 開き直した直後：切れた行を閉じる改行と、次の行の頭出しが要る
  uint32_t lastTryMs = 0;  // 最後に開き直しを試した時刻（millis）
  uint32_t tries = 0;      // 書けなくなってから開き直しを試した回数
};

struct SdWriteResult {
  size_t written = 0;  // SD に渡せたバイト数（区切りの改行を含む）
  uint32_t errors = 0; // 書けなかった回数（status.csv の sd_write_errors に足す）
};

// d[from, n) の中で、次の行の頭の位置。改行が無ければ n
inline size_t nextLineStart(const char *d, size_t from, size_t n) {
  for (size_t i = from; i < n; i++)
    if (d[i] == '\n') return i + 1;
  return n;
}

template <class Sink>
bool sdTryReopen(Sink &sink, SdFileGuard &g, uint32_t nowMs) {
  g.tries++;
  g.lastTryMs = nowMs;
  if (!sink.reopen()) {
    g.broken = true;
    return false;
  }
  char d[48];
  snprintf(d, sizeof(d), "file=%s tries=%lu", sink.name(), (unsigned long)g.tries);
  sink.logEvent("sd_reopen", d);
  g.broken = false;
  g.needSeam = true;
  g.tries = 0;
  return true;
}

// 書けなくなっているファイルを、時間が来ていれば開き直す。書いてよければ true
template <class Sink>
bool sdEnsureWritable(Sink &sink, SdFileGuard &g, uint32_t nowMs) {
  if (!g.broken) return true;
  if (nowMs - g.lastTryMs < SD_REOPEN_RETRY_MS) return false;
  return sdTryReopen(sink, g, nowMs);
}

// d[0, n) を書く。書けなければ 1 度だけその場で開き直して続きを書く。それでもだめなら残りは捨て、broken にする
template <class Sink>
SdWriteResult sdWriteChunk(Sink &sink, SdFileGuard &g, const char *d, size_t n, uint32_t nowMs) {
  SdWriteResult r;
  size_t from = 0;
  for (;;) {
    bool ok = true;
    if (g.needSeam) {
      from = nextLineStart(d, from, n);
      if (from == n) return r;  // 行の頭がまだ来ていない。次のかたまりで探す
      ok = sink.write("\n", 1) == 1;
      if (ok) {
        r.written++;
        g.needSeam = false;
      }
    }
    if (ok) {
      size_t w = sink.write(d + from, n - from);
      r.written += w;
      from += w;
      if (from == n) return r;
    }
    // 書けなかった。書けた分の最後の行は途中で切れているかもしれないので、開き直したら行の頭から書く
    r.errors++;
    if (r.errors == 1) {
      char detail[48];
      snprintf(detail, sizeof(detail), "file=%s", sink.name());
      sink.logEvent("sd_write_error", detail);
    }
    g.needSeam = true;
    if (r.errors > 1 || !sdTryReopen(sink, g, nowMs)) {
      g.broken = true;
      g.lastTryMs = nowMs;
      return r;
    }
  }
}
