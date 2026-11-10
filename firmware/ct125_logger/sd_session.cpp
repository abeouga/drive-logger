#include "sd_session.h"

#include "accel_sampler.h"
#include "event_log.h"
#include "gps_task.h"
#include "logger_constants.h"
#include "logger_state.h"

File fAccel, fGps, fEvent;
String sessionDir;

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

static File openCsv(const char *name, const char *header) {
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
