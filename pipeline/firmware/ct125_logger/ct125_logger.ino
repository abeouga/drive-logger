// CT125ロガー フェーズ1：加速度（ADXL345）＋GPS（ATGM336H）を microSD に記録する
// データの形は ../../データ仕様.md（v2）に合わせている。
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
// LED（PC なしで動かすときの目印）
//   ゆっくり点滅（1秒に1回）      : 記録中・GPS 有効
//   短く2回ずつ点滅              : 記録中・GPS まだ（未測位）
//   速い点滅（1秒に5回）が続く     : 記録できていない（SD・ADXL のどちらかが NG）

#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include "freertos/ringbuf.h"
#include "esp_timer.h"

#define FW_VERSION "CT125_LOGGER_V2.1"

const int PIN_SDA = 21, PIN_SCL = 22;
const int PIN_GPS_RX = 32, PIN_GPS_TX = 33;
const int PIN_PPS = -1;              // PPS をつないだら 34 などにする（-1＝使わない）
const int PIN_LED = 2;
const uint32_t GPS_BAUD = 9600;
const int PIN_SD_CS = 5;
const uint32_t SD_HZ = 4000000;
const uint8_t ADXL = 0x53;
const float G_PER_LSB = 0.0039f;     // フル分解能
const float ACCEL_HZ = 400.0f;       // BW_RATE=0x0C
const uint32_t FLUSH_MS = 1000;
const uint32_t STATUS_MS = 10000;

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
  for (;;) {
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
      len += snprintf(buf + len, sizeof(buf) - len, "%lu,%lld,%.4f,%.4f,%.4f\n", (unsigned long)samples,
                      (long long)tUs, x * G_PER_LSB, y * G_PER_LSB, z * G_PER_LSB);
      samples++;
      got++;
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
void ledTask(void *) {
  pinMode(PIN_LED, OUTPUT);
  for (;;) {
    if (!running) {                       // NG：速い点滅
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
  Serial.println("LOGGING (電源を切れば終了。直前約1秒までは保存されます)");
}

void loop() {
  if (!running) {
    delay(1000);
    return;
  }
  static uint32_t lastFlush = millis(), lastStatus = millis();
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
}
