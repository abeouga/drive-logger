#include "sd_session.h"

#include "accel_sampler.h"
#include "ecu_reader.h"
#include "event_log.h"
#include "gps_task.h"
#include "logger_constants.h"
#include "logger_state.h"

CsvFile csvAccel{"accel.csv"}, csvGps{"gps.csv"}, csvEvent{"events.csv"};
CsvFile csvEcu{"ecu.csv"};
String sessionDir;

// sd_write_recovery.h が書き込み・開き直し・出来事の記録に使う
struct CsvSink {
  CsvFile &c;
  size_t write(const char *d, size_t n) { return c.file.write((const uint8_t *)d, n); }
  bool reopen() {
    c.file.close();  // 閉じると FatFs のファイルのエラーが消える
    c.file = SD.open(sessionDir + "/" + c.name, FILE_APPEND);
    return (bool)c.file;
  }
  const char *name() const { return c.name; }
  void logEvent(const char *type, const char *detail) { ::logEvent(type, detail); }
};

void listSessions() {
  File dir = SD.open("/sessions");
  if (!dir) return;
  Serial.println("===SESSIONS===");
  for (File d = dir.openNextFile(); d; d = dir.openNextFile()) {
    if (!d.isDirectory()) continue;
    String base = String("/sessions/") + d.name();
    File a = SD.open(base + "/accel.csv"), g = SD.open(base + "/gps.csv");
    if (!a) a = SD.open(base + "/sensors.csv");   // 古い形（V1）の記録を一覧に出すため
    Serial.printf("  %s accel=%u gps=%u bytes\n", d.name(), a ? (unsigned)a.size() : 0, g ? (unsigned)g.size() : 0);
    if (a) a.close();
    if (g) g.close();
  }
  Serial.println("===SESSIONS_END===");
}

static File openCsv(const char *name, const char *header) {
  File f = SD.open(sessionDir + "/" + name, FILE_WRITE);
  if (f) {
    f.println(header);
    f.flush();
  }
  return f;
}

bool openSession(bool ecu) {
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
    m.printf("  \"accel\": {\"chip\": \"ADXL345\", \"bus\": \"i2c\", \"odr_hz\": %.0f, \"range_g\": 16, \"lsb_g\": 0.0039, \"unit\": \"g\", "
             "\"axes\": \"センサー基板の軸のまま\"},\n", ACCEL_HZ);
    m.printf("  \"gps\": {\"chip\": \"ATGM336H\", \"baud\": %lu, \"t_rx_us\": \"RMC文の先頭を受け取った時刻\", "
             "\"pps_pin\": %d},\n", (unsigned long)GPS_BAUD, PIN_PPS);
    m.printf("  \"ecu\": {\"adapter\": \"ELM327\", \"link\": \"bluetooth_spp\", \"configured\": %s},\n", ecu ? "true" : "false");
    m.printf("  \"mounting\": \"未記入（取り付けたら notes.md に書く）\",\n  \"flush_ms\": %lu\n}\n",
             (unsigned long)FLUSH_MS);
    m.close();
  }
  csvAccel.file = openCsv("accel.csv", "n,t_us,ax_g,ay_g,az_g");
  csvGps.file = openCsv("gps.csv", PIN_PPS >= 0
                                ? "t_rx_us,utc,date,status,fix,sats,hdop,lat,lon,speed_kmh,course_deg,pps_us"
                                : "t_rx_us,utc,date,status,fix,sats,hdop,lat,lon,speed_kmh,course_deg");
  csvEvent.file = openCsv("events.csv", "t_us,type,detail");
  if (ecu) csvEcu.file = openCsv("ecu.csv", "t_us,pid,value,raw");
  File s = openCsv("status.csv",
                   "t_us,samples,rate_hz,ring_drops,fifo_overruns,i2c_errors,sd_write_errors,bytes,gps_status,gps_sats,"
                   "period_us,dt_min_us,dt_max_us,pll_err_max_us,time_resyncs");
  if (s) s.close();
  if (csvEvent.file && pendingEvents.length()) {
    csvEvent.file.print(pendingEvents);
    csvEvent.file.flush();
  }
  return csvAccel.file && csvGps.file && csvEvent.file;
}

void drain(RingbufHandle_t r, CsvFile &c, TickType_t wait) {
  CsvSink sink{c};
  if (!sdEnsureWritable(sink, c.guard, millis())) {
    if (wait) vTaskDelay(wait);  // 取り出さないときも、待つはずだった分は待つ（loop() が空回りしないように）
    return;
  }
  size_t n = 0;
  char *data = (char *)xRingbufferReceiveUpTo(r, &n, wait, 4096);
  if (!data) return;
  SdWriteResult res = sdWriteChunk(sink, c.guard, data, n, millis());
  sdWriteErrors += res.errors;
  bytesWritten += res.written;
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
  Serial.printf("ECU connected=%d reads=%lu errors=%lu heap_free=%u heap_min=%u\n", ecuConnected ? 1 : 0,
                (unsigned long)ecuReads, (unsigned long)ecuErrors, (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
  File s = SD.open(sessionDir + "/status.csv", FILE_APPEND);
  if (s) {
    s.println(buf);
    s.close();
  }
}
