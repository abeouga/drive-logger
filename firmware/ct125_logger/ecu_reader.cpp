#include "ecu_reader.h"

#include <BluetoothSerial.h>

#include "elm_parse.h"
#include "event_log.h"
#include "logger_state.h"

RingbufHandle_t ringEcu = nullptr;
volatile bool ecuStopped = true;
volatile bool ecuConnected = false;
volatile uint32_t ecuReads = 0, ecuErrors = 0;

namespace {

BluetoothSerial elmBt;
uint8_t elmAddress[6];
const char *ELM_PIN = "1234";            // アダプターの説明書の既定のパスキー（秘密ではない）
const uint32_t RETRY_MS = 10000;         // つながらない・切れたときに、つなぎ直すまでの間
const uint32_t REPLY_TIMEOUT_MS = 2000;  // 1 つの要求の返事を待つ時間（ふだんは約 0.16 秒）
const uint32_t INIT_TIMEOUT_MS = 15000;  // ECU の初期化（0100）の返事を待つ時間（ふだんは約 0.8 秒）
const int MAX_MISSES = 3;                // 返事が続けてこれだけ来なければ、切れたとみなす

// 1 つの命令を送り、プロンプト（>）まで読む。返事は改行をスペースにして reply に入れる。時間切れなら false
bool transact(const char *cmd, char *reply, size_t size, uint32_t timeoutMs) {
  reply[0] = '\0';
  if (!elm::allowedCommand(cmd)) return false;  // ここで止める（送らない）
  while (elmBt.available()) elmBt.read();
  elmBt.print(cmd);
  elmBt.print('\r');
  size_t n = 0;
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    if (stopRequested) return false;
    while (elmBt.available()) {
      char c = (char)elmBt.read();
      if (c == '>') {
        while (n > 0 && reply[n - 1] == ' ') n--;
        reply[n] = '\0';
        return true;
      }
      if (c == '\r' || c == '\n' || c == ',') c = ' ';  // CSV の 1 列に入れるので、改行とカンマを持ち込まない
      if (c == ' ' && (n == 0 || reply[n - 1] == ' ')) continue;
      if (n < size - 1 && isprint((unsigned char)c)) reply[n++] = c;
    }
    vTaskDelay(pdMS_TO_TICKS(1));
  }
  reply[n] = '\0';
  return false;
}

// アダプターを初期化し、ECU が応答するか確かめる（#127 と同じ手順）
bool initElm() {
  char reply[96];
  static const char *const SETUP[] = {"ATZ", "ATE0", "ATH0", "ATSP5", "ATAT2"};
  for (const char *c : SETUP) {
    if (!transact(c, reply, sizeof(reply), 3000)) return false;
  }
  bool ok = transact("0100", reply, sizeof(reply), INIT_TIMEOUT_MS) && strstr(reply, "41 00");
  if (!ok) {
    char d[48];
    snprintf(d, sizeof(d), "reply=%.36s", reply);
    logEvent("ecu_init_ng", d);
  }
  return ok;
}

void pushLine(int64_t tUs, const char *pid, bool hasValue, float value, const char *reply) {
  char line[128];
  char v[16] = "";
  if (hasValue) snprintf(v, sizeof(v), strcmp(pid, "42") == 0 ? "%.3f" : "%.2f", value);
  int len = snprintf(line, sizeof(line), "%lld,%s,%s,%.80s\n", (long long)tUs, pid, v, reply);
  if (len > (int)sizeof(line) - 1) len = sizeof(line) - 1;
  if (!stopRequested) pushTo(ringEcu, line, len);
}

void ecuTask(void *) {
  uint32_t lastTry = 0;
  bool first = true;
  for (;;) {
    if (stopRequested) break;
    if (!first && millis() - lastTry < RETRY_MS) {
      vTaskDelay(pdMS_TO_TICKS(200));
      continue;
    }
    first = false;
    lastTry = millis();
    uint32_t t0 = millis();
    if (!elmBt.connect(elmAddress) || stopRequested) continue;
    if (!initElm()) {
      elmBt.disconnect();
      continue;
    }
    char d[24];
    snprintf(d, sizeof(d), "ms=%lu", (unsigned long)(millis() - t0));
    logEvent("ecu_connected", d);
    ecuConnected = true;
    elm::Schedule schedule;
    int misses = 0;
    const char *reason = nullptr;
    while (!stopRequested) {
      if (!elmBt.connected()) {
        reason = "reason=disconnected";
        break;
      }
      elm::Item item = schedule.next(millis());
      char reply[96];
      bool got = transact(item.cmd, reply, sizeof(reply), REPLY_TIMEOUT_MS);
      if (stopRequested) break;
      int64_t t = nowUs();
      uint8_t bytes[4];
      float value = 0;
      int n = got ? elm::replyBytes(reply, item.pid, bytes, 4) : -1;
      bool ok = n > 0 && elm::decode(item.pid, bytes, n, &value);
      pushLine(t, item.pid, ok, value, got ? reply : "TIMEOUT");
      if (ok) {
        ecuReads = ecuReads + 1;
        misses = 0;
      } else {
        ecuErrors = ecuErrors + 1;
        if (++misses >= MAX_MISSES) {
          reason = "reason=no_reply";
          break;
        }
      }
    }
    ecuConnected = false;
    if (!stopRequested) logEvent("ecu_lost", reason ? reason : "reason=unknown");
    elmBt.disconnect();
    lastTry = millis();
  }
  ecuConnected = false;
  elmBt.end();  // Bluetooth を止めてメモリを空ける（この後 Wi-Fi・HTTPS で送る）
  ecuStopped = true;
  vTaskDelete(nullptr);
}

}  // namespace

bool parseBtAddress(const String &text, uint8_t out[6]) {
  if (text.length() != 17) return false;
  for (int i = 0; i < 6; i++) {
    char h[3] = {text[i * 3], text[i * 3 + 1], '\0'};
    if (!isxdigit((unsigned char)h[0]) || !isxdigit((unsigned char)h[1])) return false;
    if (i < 5 && text[i * 3 + 2] != ':') return false;
    out[i] = (uint8_t)strtol(h, nullptr, 16);
  }
  return true;
}

bool startEcuTask(const String &address) {
  if (!parseBtAddress(address, elmAddress)) return false;
  // BLE は使わないので、そのメモリを手放す（Bluetooth Classic だけにする）
  if (!elmBt.begin("ct125-logger", true, true)) return false;
  elmBt.setPin(ELM_PIN, strlen(ELM_PIN));
  ecuStopped = false;
  xTaskCreatePinnedToCore(ecuTask, "ecu", 6144, nullptr, 2, nullptr, 1);
  return true;
}
