#include "gps_task.h"

#include "event_log.h"
#include "logger_constants.h"
#include "logger_state.h"
#include "nmea.h"

volatile char gpsStatus = 'V';
volatile int gpsSats = 0;
volatile int64_t ppsUs = -1;
volatile float gpsSpeedKmh = -1;

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
