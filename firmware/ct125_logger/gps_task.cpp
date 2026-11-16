#include "gps_task.h"

#include "event_log.h"
#include "logger_constants.h"
#include "logger_state.h"
#include "nmea.h"

volatile char gpsStatus = 'V';
volatile int gpsSats = 0;
volatile int64_t ppsUs = -1;
volatile float gpsSpeedKmh = -1;
volatile int64_t statGpsSecSumUs = 0;
volatile int32_t statGpsSecN = 0;
volatile int32_t statGpsElapsedS = 0, statEspPerGpsPpm = 0;
volatile float statAdxlHzGps = 0;

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
        // 診断（#132）：RMC は GPS の 1 秒ごとに来る。受けた間隔（ESP32 の時計）を足していく。1 秒前後のときだけ数える
        static int64_t lastRmcUs = -1;
        if (lastRmcUs >= 0) {
          int64_t d = lineStartUs - lastRmcUs;
          if (d > 900000 && d < 1100000) {
            statGpsSecSumUs += d;
            statGpsSecN = statGpsSecN + 1;
          }
        }
        lastRmcUs = lineStartUs;
        // 診断（#132）：記録の始めからの累計。GPS の時刻で何秒たったか・ESP32 の時計で何 µs たったか・加速度が何件来たか
        {
          String u = nmeaField(line, 1);
          char stc = nmeaField(line, 2).length() ? nmeaField(line, 2)[0] : 'V';
          if (stc == 'A' && u.length() >= 6) {
            long sod = u.substring(0, 2).toInt() * 3600L + u.substring(2, 4).toInt() * 60L + u.substring(4, 6).toInt();
            static long sod0 = -1;
            static int64_t t0 = 0;
            static uint32_t s0 = 0;
            if (sod0 < 0) {
              sod0 = sod;
              t0 = lineStartUs;
              s0 = samples;
            } else {
              long dSec = sod - sod0;
              if (dSec < 0) dSec += 86400;
              if (dSec > 0) {
                statGpsElapsedS = dSec;
                statEspPerGpsPpm = (int32_t)(((double)(lineStartUs - t0) - dSec * 1e6) / dSec);
                statAdxlHzGps = (float)((double)(samples - s0) / dSec);
              }
            }
          }
        }
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
