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
#include <math.h>
#include "freertos/ringbuf.h"
#include "esp_timer.h"
#include "config_store.h"
#include "uploader.h"

#define FW_VERSION "CT125_LOGGER_V3.1"

const int PIN_SDA = 21, PIN_SCL = 22;
const int PIN_GPS_RX = 32, PIN_GPS_TX = 33;
const int PIN_PPS = -1;              // PPS をつないだら 34 などにする（-1＝使わない）
const int PIN_LED = 2;
const int PIN_BOOT = 0;              // 開発ボードの BOOT ボタン（押すと LOW）。起動後は普通の入力として使える
const uint32_t GPS_BAUD = 9600;
const int PIN_SD_CS = 5;
const uint32_t SD_HZ = 4000000;
const uint8_t ADXL = 0x53;
const float G_PER_LSB = 0.0039f;     // フル分解能
const float ACCEL_HZ = 400.0f;       // BW_RATE=0x0C
const uint32_t FLUSH_MS = 1000;
const uint32_t STATUS_MS = 10000;

// 送信のきっかけ（設計書 3.1）
const float QUIET_STD_G = 0.02f;        // 1 秒間の合成加速度のばらつきがこれ未満なら「静か」（エンジン停止。静止時の雑音は約 0.008g）
const float MOVING_STD_G = 0.05f;       // これを超えたら「動いている」（アイドリングや走行）
const float STOP_SPEED_KMH = 3.0f;      // GPS 速度がこれ未満なら止まっている
const uint32_t QUIET_SECONDS = 120;     // 静かな状態がこれだけ続いたら記録を閉じて送る
const uint32_t BUTTON_HOLD_MS = 2000;   // BOOT ボタンをこれだけ押し続けたら、今すぐ送る
const uint32_t MOVING_SECONDS_TO_WAKE = 3;  // 待機中、これだけ続けて動いたら再起動して記録を始める

// 動作の状態
enum Mode { MODE_ERROR, MODE_LOGGING, MODE_UPLOADING, MODE_IDLE };
volatile Mode mode = MODE_ERROR;
volatile UploadResult lastUploadResult = UploadResult::NothingToSend;

static inline int64_t nowUs() { return esp_timer_get_time(); }

// ファイルごとのリングバッファ（加速度は大きく、ほかは小さく）
RingbufHandle_t ringAccel, ringGps, ringEvent;
File fAccel, fGps, fEvent;
String sessionDir;

volatile uint32_t samples = 0, ringDrops = 0, fifoOverruns = 0, i2cErrors = 0, sdWriteErrors = 0;
volatile uint64_t bytesWritten = 0;
volatile int64_t firstSampleUs = -1, lastSampleUs = -1;
volatile char gpsStatus = 'V';
volatile int gpsSats = 0;
volatile int64_t ppsUs = -1;
bool running = false;

// 記録を閉じるとき、加速度と GPS のタスクに止まってもらう
volatile bool stopRequested = false, accelStopped = false, gpsStopped = false;
// 送信のきっかけの判定に使う値（sensorTask・gpsTask が更新する）
volatile float accelStd1s = -1;      // 直近 1 秒の合成加速度の標準偏差 [g]
volatile float gpsSpeedKmh = -1;     // GPS 速度（無効なら -1）
volatile bool hasMoved = false;      // この走行で一度でも動いたか（止まったまま電源を入れただけの走行は閉じない）

// 起動前（SDが開く前）の出来事はここにためて、セッション作成後に書く
String pendingEvents;

void pushTo(RingbufHandle_t r, const char *s, int len) {
  if (!r || xRingbufferSend(r, s, len, 0) != pdTRUE) ringDrops++;
}

void logEvent(const char *type, const char *detail) {
  char line[128];
  int len = snprintf(line, sizeof(line), "%lld,%s,%s\n", (long long)nowUs(), type, detail);
  Serial.printf("EVENT %s", line);
  if (running) pushTo(ringEvent, line, len);
  else pendingEvents += line;
}

// ------------------------------------------------------------------ ADXL345
bool readRegs(uint8_t reg, uint8_t *buf, uint8_t n) {
  Wire.beginTransmission(ADXL);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ADXL, n) != n) return false;
  for (int i = 0; i < n; i++) buf[i] = Wire.read();
  return true;
}

bool writeReg(uint8_t reg, uint8_t v) {
  Wire.beginTransmission(ADXL);
  Wire.write(reg);
  Wire.write(v);
  return Wire.endTransmission() == 0;
}

// ESPだけがリセットされると、ADXLが読み出しの途中でSDAをLOWにつかんだまま残ることがある。
// SCLを最大9回動かしてADXLに残りのビットを吐き出させ、STOPを送って線を解放する。
void i2cBusRecover() {
  pinMode(PIN_SDA, INPUT_PULLUP);
  pinMode(PIN_SCL, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_SCL, HIGH);
  delayMicroseconds(10);
  for (int i = 0; i < 9 && digitalRead(PIN_SDA) == LOW; i++) {
    digitalWrite(PIN_SCL, LOW);
    delayMicroseconds(10);
    digitalWrite(PIN_SCL, HIGH);
    delayMicroseconds(10);
  }
  pinMode(PIN_SDA, OUTPUT_OPEN_DRAIN);   // STOP: SCL=HIGH のまま SDA を LOW→HIGH
  digitalWrite(PIN_SDA, LOW);
  delayMicroseconds(10);
  digitalWrite(PIN_SDA, HIGH);
  delayMicroseconds(10);
  pinMode(PIN_SDA, INPUT);
  pinMode(PIN_SCL, INPUT);
}

bool adxlInit() {
  uint8_t id = 0;
  for (int attempt = 1; attempt <= 5; attempt++) {
    id = 0;
    if (readRegs(0x00, &id, 1) && id == 0xE5) break;
    char d[32];
    snprintf(d, sizeof(d), "attempt=%d devid=0x%02X", attempt, id);
    logEvent("adxl_retry", d);
    Wire.end();
    i2cBusRecover();
    Wire.begin(PIN_SDA, PIN_SCL, 400000);
    delay(20);
  }
  if (id != 0xE5) return false;
  writeReg(0x2D, 0x00);        // 設定中は停止
  writeReg(0x31, 0x0B);        // DATA_FORMAT: FULL_RES, ±16g
  writeReg(0x2C, 0x0C);        // BW_RATE: 400Hz
  writeReg(0x38, 0x00);        // FIFO を空にする（バイパス）
  writeReg(0x38, 0x80 | 16);   // FIFO_CTL: ストリームモード
  writeReg(0x2D, 0x08);        // POWER_CTL: 測定開始
  return true;
}

// ------------------------------------------------------------------ GPS
String nmeaField(const String &s, int n) {
  int start = 0;
  for (int i = 0; i < n; i++) {
    start = s.indexOf(',', start);
    if (start < 0) return "";
    start++;
  }
  int end = s.indexOf(',', start);
  int star = s.indexOf('*', start);
  if (end < 0 || (star >= 0 && star < end)) end = star;
  return s.substring(start, end < 0 ? s.length() : end);
}

String nmeaDeg(const String &v, const String &hemi) {
  if (v.length() < 4) return "";
  double x = v.toDouble();
  int d = (int)(x / 100);
  double deg = d + (x - d * 100) / 60.0;
  if (hemi == "S" || hemi == "W") deg = -deg;
  char b[16];
  snprintf(b, sizeof(b), "%.7f", deg);
  return b;
}

bool nmeaChecksumOk(const String &s) {
  int star = s.indexOf('*');
  if (!s.startsWith("$") || star < 0) return false;
  uint8_t c = 0;
  for (int i = 1; i < star; i++) c ^= s[i];
  return strtol(s.substring(star + 1).c_str(), nullptr, 16) == c;
}

void IRAM_ATTR onPps() { ppsUs = esp_timer_get_time(); }

void gpsTask(void *) {
  Serial2.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
  String line;
  int64_t lineStartUs = 0;
  String ggaFix = "", ggaSats = "", ggaHdop = "";
  char prevStatus = 'V';
  for (;;) {
    if (stopRequested) {
      gpsStopped = true;
      vTaskDelete(nullptr);
    }
    while (Serial2.available()) {
      char c = Serial2.read();
      if (c == '$') {
        line = "";
        lineStartUs = nowUs();
      }
      if (c != '\n') {
        if (line.length() < 120) line += c;
        continue;
      }
      line.trim();
      if (!nmeaChecksumOk(line)) continue;
      String type = line.substring(3, 6);
      if (type == "GGA") {
        ggaFix = nmeaField(line, 6);
        ggaSats = nmeaField(line, 7);
        ggaHdop = nmeaField(line, 8);
        gpsSats = ggaSats.toInt();
      } else if (type == "RMC") {
        String st = nmeaField(line, 2);
        char status = st.length() ? st[0] : 'V';
        String sp = nmeaField(line, 7);
        char speed[12] = "";
        if (sp.length()) snprintf(speed, sizeof(speed), "%.2f", sp.toFloat() * 1.852f);
        char out[200];
        int len = snprintf(out, sizeof(out), "%lld,%s,%s,%c,%s,%s,%s,%s,%s,%s,%s",
                           (long long)lineStartUs, nmeaField(line, 1).c_str(), nmeaField(line, 9).c_str(), status,
                           ggaFix.c_str(), ggaSats.c_str(), ggaHdop.c_str(),
                           status == 'A' ? nmeaDeg(nmeaField(line, 3), nmeaField(line, 4)).c_str() : "",
                           status == 'A' ? nmeaDeg(nmeaField(line, 5), nmeaField(line, 6)).c_str() : "",
                           speed, nmeaField(line, 8).c_str());
        if (PIN_PPS >= 0) len += snprintf(out + len, sizeof(out) - len, ",%lld", (long long)ppsUs);
        len += snprintf(out + len, sizeof(out) - len, "\n");
        pushTo(ringGps, out, len);
        gpsSpeedKmh = (status == 'A' && sp.length()) ? sp.toFloat() * 1.852f : -1.0f;
        if (gpsSpeedKmh > 10.0f) hasMoved = true;
        gpsStatus = status;
        if (status != prevStatus) logEvent(status == 'A' ? "gps_valid" : "gps_lost", "");
        prevStatus = status;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
}

// ------------------------------------------------------------------ 加速度（コア0）
// 時刻の付け方（V2.1）
//   V2 は FIFO を読んだ瞬間の時刻を付けていたため、ESP が FIFO を見に行く間隔（約1ms）で
//   時刻が丸められ、間隔が 2ms／3ms に割れていた（ride_019 で確認）。
//   V2.1 では「前のサンプルの時刻＋周期」で時刻を進め、読んだ時刻とのずれ（err）は
//   少しずつだけ時刻と周期に戻す（PLL）。間隔はなめらかになり、長時間でも ESP の時計からずれない。
//   ずれが 20ms を超えたら（長い停止のあとなど）、合わせ直して events.csv に time_resync を残す。
const double PLL_KP = 0.02;     // 時刻の補正の強さ
const double PLL_KF = 0.0001;   // 周期の補正の強さ
const double RESYNC_US = 20000;
volatile double pllPeriodUs = 1e6 / ACCEL_HZ;
volatile int32_t statDtMin = INT32_MAX, statDtMax = 0, statErrMax = 0;
volatile uint32_t timeResyncs = 0;

void sensorTask(void *) {
  char buf[64 * 33];
  uint8_t raw[6];
  double periodUs = 1e6 / ACCEL_HZ;   // 実測に合わせて PLL が更新する
  double tNext = -1;                  // 次のサンプルに付ける時刻
  int64_t tPrev = -1;
  // 設定から記録開始までの間に FIFO があふれているので、空にしてから始める
  writeReg(0x38, 0x00);
  writeReg(0x38, 0x80 | 16);
  uint8_t clr;
  readRegs(0x30, &clr, 1);
  // 1 秒ごとの合成加速度のばらつき（送信のきっかけの判定用）
  double magSum = 0, magSumSq = 0;
  int magCount = 0;
  for (;;) {
    if (stopRequested) {
      accelStopped = true;
      vTaskDelete(nullptr);
    }
    uint8_t st = 0, src = 0;
    if (!readRegs(0x39, &st, 1) || !readRegs(0x30, &src, 1)) {
      i2cErrors++;
      vTaskDelay(1);
      continue;
    }
    if ((src & 0x01) && samples > 0) {   // 記録開始前（n=0）のあふれは記録の欠けではないので数えない
      fifoOverruns++;
      char d[24];
      snprintf(d, sizeof(d), "n=%lu", (unsigned long)samples);
      logEvent("fifo_overrun", d);
    }
    int n = st & 0x3F;
    if (n < 4) {                      // 数件たまってからまとめて読む（FIFO は32件＝約80ms分あるので余裕あり）
      vTaskDelay(2);
      continue;
    }
    int64_t now = nowUs();
    // いちばん新しいサンプルは、読んだ時刻の「0〜1周期前」にできている → 平均して半周期前とみなす
    double expectedLast = now - periodUs * 0.5;
    if (tNext < 0) tNext = expectedLast - (n - 1) * periodUs;
    double err = expectedLast - (tNext + (n - 1) * periodUs);
    if (fabs(err) > RESYNC_US) {
      char d[40];
      snprintf(d, sizeof(d), "err_us=%.0f n=%lu", err, (unsigned long)samples);
      logEvent("time_resync", d);
      timeResyncs++;
      tNext = expectedLast - (n - 1) * periodUs;
      err = 0;
    } else {
      tNext += PLL_KP * err;
      periodUs += PLL_KF * err;
    }
    if (fabs(err) > statErrMax) statErrMax = (int32_t)fabs(err);
    int len = 0, got = 0;
    for (int i = 0; i < n; i++) {
      if (!readRegs(0x32, raw, 6)) {
        i2cErrors++;
        break;
      }
      int16_t x = raw[0] | (raw[1] << 8), y = raw[2] | (raw[3] << 8), z = raw[4] | (raw[5] << 8);
      int64_t tUs = (int64_t)(tNext + i * periodUs);
      if (tPrev >= 0) {
        int32_t dt = (int32_t)(tUs - tPrev);
        if (dt < statDtMin) statDtMin = dt;
        if (dt > statDtMax) statDtMax = dt;
      }
      tPrev = tUs;
      if (firstSampleUs < 0) firstSampleUs = tUs;
      lastSampleUs = tUs;
      float gx = x * G_PER_LSB, gy = y * G_PER_LSB, gz = z * G_PER_LSB;
      len += snprintf(buf + len, sizeof(buf) - len, "%lu,%lld,%.4f,%.4f,%.4f\n", (unsigned long)samples,
                      (long long)tUs, gx, gy, gz);
      samples++;
      got++;
      double mag = sqrt((double)gx * gx + (double)gy * gy + (double)gz * gz);
      magSum += mag;
      magSumSq += mag * mag;
      if (++magCount >= (int)ACCEL_HZ) {
        double mean = magSum / magCount;
        double var = magSumSq / magCount - mean * mean;
        accelStd1s = (float)sqrt(var > 0 ? var : 0);
        if (accelStd1s > MOVING_STD_G) hasMoved = true;
        magSum = magSumSq = 0;
        magCount = 0;
      }
    }
    tNext += got * periodUs;
    pllPeriodUs = periodUs;
    if (len) pushTo(ringAccel, buf, len);
  }
}

// ------------------------------------------------------------------ SD
void listSessions() {
  File dir = SD.open("/sessions");
  if (!dir) return;
  Serial.println("===SESSIONS===");
  for (File d = dir.openNextFile(); d; d = dir.openNextFile()) {
    if (!d.isDirectory()) continue;
    String base = String("/sessions/") + d.name();
    File a = SD.open(base + "/accel.csv"), g = SD.open(base + "/gps.csv");
    if (!a) a = SD.open(base + "/sensors.csv");   // V1 の記録
    Serial.printf("  %s accel=%u gps=%u bytes\n", d.name(), a ? (unsigned)a.size() : 0, g ? (unsigned)g.size() : 0);
    if (a) a.close();
    if (g) g.close();
  }
  Serial.println("===SESSIONS_END===");
}

File openCsv(const char *name, const char *header) {
  File f = SD.open(sessionDir + "/" + name, FILE_WRITE);
  if (f) {
    f.println(header);
    f.flush();
  }
  return f;
}

bool openSession() {
  SD.mkdir("/sessions");
  for (int i = 1; i < 1000; i++) {
    char p[32];
    snprintf(p, sizeof(p), "/sessions/ride_%03d", i);
    if (!SD.exists(p)) {
      sessionDir = p;
      break;
    }
  }
  if (sessionDir.isEmpty() || !SD.mkdir(sessionDir)) return false;
  File m = SD.open(sessionDir + "/meta.json", FILE_WRITE);
  if (m) {
    m.printf("{\n  \"spec\": \"データ仕様.md v2\",\n  \"firmware\": \"%s\",\n  \"build\": \"%s %s\",\n", FW_VERSION,
             __DATE__, __TIME__);
    m.printf("  \"clock\": \"t_us = ESP32 esp_timer（起動からのマイクロ秒）\",\n");
    m.printf("  \"accel\": {\"chip\": \"ADXL345\", \"odr_hz\": %.0f, \"range_g\": 16, \"lsb_g\": 0.0039, \"unit\": \"g\", "
             "\"axes\": \"センサー基板の軸のまま\"},\n", ACCEL_HZ);
    m.printf("  \"gps\": {\"chip\": \"ATGM336H\", \"baud\": %lu, \"t_rx_us\": \"RMC文の先頭を受け取った時刻\", "
             "\"pps_pin\": %d},\n", (unsigned long)GPS_BAUD, PIN_PPS);
    m.printf("  \"mounting\": \"未記入（取り付けたら notes.md に書く）\",\n  \"flush_ms\": %lu\n}\n",
             (unsigned long)FLUSH_MS);
    m.close();
  }
  fAccel = openCsv("accel.csv", "n,t_us,ax_g,ay_g,az_g");
  fGps = openCsv("gps.csv", PIN_PPS >= 0
                                ? "t_rx_us,utc,date,status,fix,sats,hdop,lat,lon,speed_kmh,course_deg,pps_us"
                                : "t_rx_us,utc,date,status,fix,sats,hdop,lat,lon,speed_kmh,course_deg");
  fEvent = openCsv("events.csv", "t_us,type,detail");
  File s = openCsv("status.csv",
                   "t_us,samples,rate_hz,ring_drops,fifo_overruns,i2c_errors,sd_write_errors,bytes,gps_status,gps_sats,"
                   "period_us,dt_min_us,dt_max_us,pll_err_max_us,time_resyncs");
  if (s) s.close();
  if (fEvent && pendingEvents.length()) {
    fEvent.print(pendingEvents);
    fEvent.flush();
  }
  return fAccel && fGps && fEvent;
}

void drain(RingbufHandle_t r, File &f, TickType_t wait) {
  size_t n = 0;
  char *data = (char *)xRingbufferReceiveUpTo(r, &n, wait, 4096);
  if (!data) return;
  size_t w = f.write((const uint8_t *)data, n);
  if (w != n) sdWriteErrors++;
  bytesWritten += w;
  vRingbufferReturnItem(r, data);
}

void writeStatus() {
  float secs = firstSampleUs < 0 ? 0 : (lastSampleUs - firstSampleUs) / 1e6f;
  char buf[260];
  // dt_min/dt_max/pll_err_max はこの10秒間の値（時刻のなめらかさの確認用）
  snprintf(buf, sizeof(buf), "%lld,%lu,%.2f,%lu,%lu,%lu,%lu,%llu,%c,%d,%.2f,%ld,%ld,%ld,%lu", (long long)nowUs(),
           (unsigned long)samples, secs > 0 ? (samples - 1) / secs : 0, (unsigned long)ringDrops,
           (unsigned long)fifoOverruns, (unsigned long)i2cErrors, (unsigned long)sdWriteErrors,
           (unsigned long long)bytesWritten, gpsStatus, gpsSats, (double)pllPeriodUs, (long)statDtMin, (long)statDtMax,
           (long)statErrMax, (unsigned long)timeResyncs);
  statDtMin = INT32_MAX;
  statDtMax = 0;
  statErrMax = 0;
  Serial.printf("STATUS %s\n", buf);
  File s = SD.open(sessionDir + "/status.csv", FILE_APPEND);
  if (s) {
    s.println(buf);
    s.close();
  }
}

// ------------------------------------------------------------------ LED
void blink(int times, uint32_t onMs, uint32_t offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_LED, HIGH);
    vTaskDelay(pdMS_TO_TICKS(onMs));
    digitalWrite(PIN_LED, LOW);
    vTaskDelay(pdMS_TO_TICKS(offMs));
  }
}

bool uploadSucceeded() {
  return lastUploadResult == UploadResult::Done || lastUploadResult == UploadResult::NothingToSend;
}

void ledTask(void *) {
  pinMode(PIN_LED, OUTPUT);
  for (;;) {
    if (mode == MODE_UPLOADING) {         // 送信中：1 秒ついて 1 秒消える
      blink(1, 1000, 1000);
    } else if (mode == MODE_IDLE && uploadSucceeded()) {  // 送信が終わった：つきっぱなし
      digitalWrite(PIN_LED, HIGH);
      vTaskDelay(pdMS_TO_TICKS(200));
    } else if (mode == MODE_IDLE) {       // 送れなかった：短く 3 回
      blink(3, 80, 150);
      vTaskDelay(pdMS_TO_TICKS(800));
    } else if (!running) {                // NG：速い点滅
      digitalWrite(PIN_LED, !digitalRead(PIN_LED));
      vTaskDelay(pdMS_TO_TICKS(100));
    } else if (gpsStatus == 'A') {        // 記録中・GPS 有効：ゆっくり点滅
      digitalWrite(PIN_LED, HIGH);
      vTaskDelay(pdMS_TO_TICKS(100));
      digitalWrite(PIN_LED, LOW);
      vTaskDelay(pdMS_TO_TICKS(900));
    } else {                              // 記録中・GPS まだ：短く2回
      for (int i = 0; i < 2; i++) {
        digitalWrite(PIN_LED, HIGH);
        vTaskDelay(pdMS_TO_TICKS(80));
        digitalWrite(PIN_LED, LOW);
        vTaskDelay(pdMS_TO_TICKS(150));
      }
      vTaskDelay(pdMS_TO_TICKS(540));
    }
  }
}

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

// ------------------------------------------------------------------ シリアルのコマンド（設定と、手動の送信）
// CFG ...（config_store.cpp）、UPLOAD（BOOT ボタンと同じ）、LOG（送信の記録の最後の 40 行）を受け付ける。
// 記録を止めないよう、届いた分だけ読む
bool uploadRequestedBySerial = false;

void printUploadLog() {
  File f = SD.open("/upload_log.csv");
  if (!f) {
    Serial.println("LOG (no /upload_log.csv)");
    return;
  }
  const size_t tailBytes = 4096;  // 最後の約 40 行
  if (f.size() > tailBytes) {
    f.seek(f.size() - tailBytes);
    f.readStringUntil('\n');  // 途中から始まる行は捨てる
  }
  while (f.available()) Serial.printf("LOG %s\n", f.readStringUntil('\n').c_str());
  f.close();
  Serial.println("LOG_END");
}

void pollSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\n') {
      if (line.length() < 300) line += c;
      continue;
    }
    line.trim();
    if (line == "UPLOAD") uploadRequestedBySerial = true;
    else if (line == "LOG") printUploadLog();
    else if (line.length()) handleConfigCommand(line);
    line = "";
  }
}

// ------------------------------------------------------------------ BOOT ボタン
// 押し続けて BUTTON_HOLD_MS を超えたら 1 回だけ true
bool buttonHeld() {
  static uint32_t pressedAt = 0;
  static bool fired = false;
  if (digitalRead(PIN_BOOT) == HIGH) {
    pressedAt = 0;
    fired = false;
    return false;
  }
  if (pressedAt == 0) pressedAt = millis();
  if (!fired && millis() - pressedAt >= BUTTON_HOLD_MS) {
    fired = true;
    return true;
  }
  return false;
}

// ------------------------------------------------------------------ 記録中
bool isQuietNow() {
  bool stillVibration = accelStd1s >= 0 && accelStd1s < QUIET_STD_G;
  bool stopped = gpsStatus != 'A' || gpsSpeedKmh < STOP_SPEED_KMH;  // 屋内などで GPS が無いときは振動だけで見る
  return stillVibration && stopped;
}

// 送るきっかけが来たら、その理由を返す（来ていなければ nullptr）。1 秒に 1 回呼ぶ
const char *uploadTrigger(uint32_t &quietSeconds) {
  quietSeconds = isQuietNow() ? quietSeconds + 1 : 0;
  if (hasMoved && quietSeconds >= QUIET_SECONDS) return "quiet";
  return nullptr;
}

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
bool movingNow();

bool movingForAWhile() {
  for (int i = 0; i < 3; i++) {
    if (!movingNow()) return false;
    delay(300);
  }
  return true;
}

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
// 記録を止めた後も ADXL345 は測り続けている。FIFO から 40 件読んで、ばらつきで動いているかを見る
bool movingNow() {
  uint8_t raw[6];
  double sum = 0, sumSq = 0;
  int n = 0;
  for (int i = 0; i < 40; i++) {
    if (!readRegs(0x32, raw, 6)) continue;
    int16_t x = raw[0] | (raw[1] << 8), y = raw[2] | (raw[3] << 8), z = raw[4] | (raw[5] << 8);
    double mag = sqrt((double)x * x + (double)y * y + (double)z * z) * G_PER_LSB;
    sum += mag;
    sumSq += mag * mag;
    n++;
    delay(3);
  }
  if (n < 10) return false;
  double mean = sum / n;
  double var = sumSq / n - mean * mean;
  return sqrt(var > 0 ? var : 0) > MOVING_STD_G;
}

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
