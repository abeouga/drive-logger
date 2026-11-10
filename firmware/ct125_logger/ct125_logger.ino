// CT125ロガー フェーズ1：加速度（ADXL345）＋GPS（ATGM336H）を microSD に記録する
// データの形は ../../docs/data_spec_v2.md（データ仕様 v2）に合わせている。
//
// 配線（ブレッドボード版 CT125-BB-R3、2026-11-02 に実機で確認済み）
//   ADXL345 : SDA=IO21, SCL=IO22, CS=3V3, SDO=GND（I2C 0x53）
//   GPS     : GPS TX → IO32（ESP受信）, GPS RX ← IO33, 9600bps, PPS は未接続（PIN_PPS で有効化）
//   microSD : CS=IO5, SCK=IO18, MISO=IO19, MOSI=IO23（秋月105488、3.3V）
//   LED     : IO2（ボード上のLEDと仮定。要確認）
//
// 記録の仕組み
//   - 電源を入れるたびに /sessions/ride_NNN/ を作り、accel.csv・gps.csv・events.csv・status.csv に書く。
//   - すべての行に ESP の時計 t_us（起動からのマイクロ秒）を付ける。GPS の UTC は gps.csv で対応づける。
//   - 加速度は ADXL345 の FIFO を使い 400Hz で読む（コア0）。GPS は別タスク（コア1）。
//   - SDへの書き込みは loop()（コア1）で、RAMのリングバッファから取り出して行う。
//   - 1秒ごとに flush。電源が突然切れても失うのは最後の約1秒。
//
// V3：走行後に Wi-Fi で S3 へ送る（docs/device_upload_design.md）
//   記録中 →（止まって静か 2 分、または BOOT ボタン 2 秒）→ 記録を閉じる → 送信 → 待機
//   待機中に動き出したら再起動して、新しい走行の記録を始める。記録と送信は同時にしない。
//   送信の手順は uploader.cpp、Wi-Fi とトークンの設定は config_store.cpp（シリアルから書き込む）。
//
// このファイルには、起動（setup）と状態の切り替え（記録中 → 送信 → 待機）だけを置く。
// 役割ごとのファイル
//   logger_constants.h  版の名前・配線・周期・送信のきっかけのしきい値
//   logger_state.*      動作の状態と、タスクをまたぐ値（件数・止める合図・リングバッファ）
//   event_log.*         events.csv への出来事
//   adxl345.*           ADXL345 のレジスタ・I2C の線の解放・初期化
//   accel_sampler.*     加速度のタスク（時刻の補正 PLL とサンプリング）→ accel.csv
//   nmea.*・gps_task.*  NMEA の読み取りと GPS のタスク → gps.csv
//   sd_session.*        走行のフォルダー・meta.json・CSV の見出し・書き出し・status.csv
//   motion.*            静か・動き出しの判定（送信のきっかけ・送信の中断・待機からの起き上がり）
//   led.*・boot_button.*・serial_commands.*  LED・BOOT ボタン・シリアルのコマンド
//
// LED（PC なしで動かすときの目印）
//   ゆっくり点滅（1秒に1回）      : 記録中・GPS 有効
//   短く2回ずつ点滅              : 記録中・GPS まだ（未測位）
//   速い点滅（1秒に5回）が続く     : 記録できていない（SD・ADXL のどちらかが NG）
//   1秒ついて1秒消える            : 送信中
//   つきっぱなし                  : 送信が終わった（または送るものが無い）
//   短く3回ずつ点滅              : 送れなかった（Wi-Fi が無い・設定が無い・失敗。BOOT ボタンでやり直せる）

#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include "freertos/ringbuf.h"
#include "config_store.h"
#include "uploader.h"
#include "logger_constants.h"
#include "logger_state.h"
#include "event_log.h"
#include "adxl345.h"
#include "accel_sampler.h"
#include "gps_task.h"
#include "sd_session.h"
#include "motion.h"
#include "led.h"
#include "boot_button.h"
#include "serial_commands.h"

void finishSession(const char *reason);
void runUpload(bool automatic);

// ------------------------------------------------------------------ main
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("\n%s READY\n", FW_VERSION);
  pinMode(PIN_BOOT, INPUT_PULLUP);
  xTaskCreatePinnedToCore(ledTask, "led", 2048, nullptr, 1, nullptr, 1);
  logEvent("boot", FW_VERSION);
  i2cBusRecover();
  Wire.begin(PIN_SDA, PIN_SCL, 400000);
  // 書き込み中にESPだけがリセットされると、カードがしばらく応答しないことがあるので再試行する
  bool mounted = false;
  for (int attempt = 1; attempt <= 5 && !mounted; attempt++) {
    uint32_t hz = attempt <= 2 ? SD_HZ : 1000000;
    mounted = SD.begin(PIN_SD_CS, SPI, hz);
    if (!mounted) {
      char d[24];
      snprintf(d, sizeof(d), "attempt=%d", attempt);
      logEvent("sd_retry", d);
      SD.end();
      delay(300);
    }
  }
  if (!mounted) {
    Serial.println("SD_MOUNT=NG 記録しません");
    return;
  }
  Serial.printf("SD_MOUNT=OK CARD_MB=%llu\n", SD.cardSize() / (1024ULL * 1024ULL));
  listSessions();
  if (!adxlInit()) {
    Serial.println("ADXL=NG 記録しません");
    return;
  }
  Serial.println("ADXL=OK 400Hz +-16g FIFO");
  if (!openSession()) {
    Serial.println("SESSION=NG 記録しません");
    return;
  }
  Serial.printf("SESSION=%s\n", sessionDir.c_str());
  ringAccel = xRingbufferCreate(64 * 1024, RINGBUF_TYPE_BYTEBUF);
  ringGps = xRingbufferCreate(8 * 1024, RINGBUF_TYPE_BYTEBUF);
  ringEvent = xRingbufferCreate(4 * 1024, RINGBUF_TYPE_BYTEBUF);
  running = true;
  if (PIN_PPS >= 0) {
    pinMode(PIN_PPS, INPUT);
    attachInterrupt(digitalPinToInterrupt(PIN_PPS), onPps, RISING);
  }
  xTaskCreatePinnedToCore(gpsTask, "gps", 6144, nullptr, 3, nullptr, 1);
  xTaskCreatePinnedToCore(sensorTask, "accel", 6144, nullptr, 5, nullptr, 0);
  mode = MODE_LOGGING;
  Serial.println("LOGGING (電源を切れば終了。直前約1秒までは保存されます)");
}

// ------------------------------------------------------------------ 記録中
void loopLogging() {
  static uint32_t lastFlush = millis(), lastStatus = millis(), lastCheck = millis(), quietSeconds = 0;
  drain(ringAccel, fAccel, pdMS_TO_TICKS(20));
  drain(ringGps, fGps, 0);
  drain(ringEvent, fEvent, 0);
  uint32_t now = millis();
  if (now - lastFlush >= FLUSH_MS) {
    fAccel.flush();
    fGps.flush();
    fEvent.flush();
    lastFlush = now;
  }
  if (now - lastStatus >= STATUS_MS) {
    lastStatus = now;
    writeStatus();
  }
  const char *reason = nullptr;
  if (buttonHeld()) reason = "button";
  if (uploadRequestedBySerial) reason = "serial";
  if (now - lastCheck >= 1000) {
    lastCheck = now;
    const char *quiet = uploadTrigger(quietSeconds);
    if (!reason) reason = quiet;
  }
  if (reason) {
    uploadRequestedBySerial = false;
    bool automatic = strcmp(reason, "quiet") == 0;
    finishSession(reason);
    runUpload(automatic);
  }
}

// 記録を閉じる：タスクを止め、たまっている分を書き切って、ファイルを閉じ、メモリを空ける（この後 Wi-Fi を使うため）
void finishSession(const char *reason) {
  logEvent("session_end", reason);
  stopRequested = true;
  uint32_t start = millis();
  while ((!accelStopped || !gpsStopped) && millis() - start < 2000) delay(10);
  for (RingbufHandle_t ring : {ringAccel, ringGps, ringEvent}) {
    File &f = ring == ringAccel ? fAccel : ring == ringGps ? fGps : fEvent;
    for (int i = 0; i < 64; i++) drain(ring, f, 0);  // 1 回 4KB まで。64KB のリングを空にするのに足りる
  }
  writeStatus();
  fAccel.close();
  fGps.close();
  fEvent.close();
  running = false;
  vRingbufferDelete(ringAccel);
  vRingbufferDelete(ringGps);
  vRingbufferDelete(ringEvent);
  ringAccel = ringGps = ringEvent = nullptr;
  Serial.printf("SESSION_END %s reason=%s\n", sessionDir.c_str(), reason);
}

// ------------------------------------------------------------------ 送信
// 自動で始めた送信は、走り出したら（動きが約 1 秒続いたら）ファイルの合間でやめる（記録が優先）。
// 手で始めた送信（BOOT ボタン・シリアル）はやめない：ボタンを押す手で基板が揺れるので、
// 一瞬の揺れでやめると送れない（2026-11-08 の机上試験で、最初の 1 回がこれで止まった）。
bool neverAbort() { return false; }

void runUpload(bool automatic) {
  mode = MODE_UPLOADING;
  UploadSummary summary = uploadPendingSessions(loadConfig(), automatic ? movingForAWhile : neverAbort);
  lastUploadResult = summary.result;
  Serial.printf("UPLOAD_RESULT %s sent=%d failed=%d free_heap=%u\n", uploadResultName(summary.result), summary.sent, summary.failed,
                (unsigned)ESP.getFreeHeap());
  mode = MODE_IDLE;
}

// ------------------------------------------------------------------ 待機中
// 動き出したら（MOVING_SECONDS_TO_WAKE 秒続けて動いたら）再起動して、新しい走行の記録を始める
void loopIdle() {
  static uint32_t lastCheck = 0, movingSeconds = 0;
  if (buttonHeld() || uploadRequestedBySerial) {  // 送れなかったときのやり直し（手動）
    uploadRequestedBySerial = false;
    runUpload(false);
    return;
  }
  if (millis() - lastCheck < 1000) {
    delay(20);
    return;
  }
  lastCheck = millis();
  movingSeconds = movingNow() ? movingSeconds + 1 : 0;
  if (movingSeconds >= MOVING_SECONDS_TO_WAKE) {
    Serial.println("MOVING 再起動して新しい走行の記録を始めます");
    delay(100);
    ESP.restart();
  }
}

void loop() {
  pollSerial();
  switch (mode) {
    case MODE_LOGGING: loopLogging(); break;
    case MODE_IDLE: loopIdle(); break;
    default: delay(100); break;  // MODE_ERROR（SD・ADXL が NG）。設定のコマンドだけは受け付ける
  }
}
