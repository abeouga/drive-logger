#include "event_log.h"

#include "logger_state.h"

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
