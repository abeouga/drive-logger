#include "ecu_reader.h"

#include <NimBLEDevice.h>

#include "elm_parse.h"
#include "event_log.h"
#include "logger_state.h"

RingbufHandle_t ringEcu = nullptr;
volatile bool ecuStopped = true;
volatile bool ecuConnected = false;
volatile uint32_t ecuReads = 0, ecuErrors = 0;

namespace {

// ELM327 互換アダプターの BLE のサービス（#129 で確かめた：FFF2 に書き、FFF1 の通知で返事が来る）
const char *SERVICE_UUID = "FFF0";
const char *NOTIFY_UUID = "FFF1";
const char *WRITE_UUID = "FFF2";
// BLE を始める前に要る空きメモリ。NimBLE は実測で約 2 万バイト使う（#129）。足りなければ始めない（落ちないように）。
// 加速度・GPS のタスク（計約 12 KB）と ECU のタスク（6 KB）を作る前に確かめるので、その分と余裕を含める
const uint32_t MIN_FREE_HEAP = 52000;
const uint32_t MIN_LARGEST_BLOCK = 16000;
const uint32_t RETRY_MS = 10000;         // つながらない・切れたときに、つなぎ直すまでの間
const uint32_t REPLY_TIMEOUT_MS = 2000;  // 1 つの要求の返事を待つ時間（ふだんは約 0.2 秒）
const uint32_t INIT_TIMEOUT_MS = 15000;  // ECU の初期化（0100）の返事を待つ時間（ふだんは約 0.8 秒）
const int MAX_MISSES = 3;                // 返事が続けてこれだけ来なければ、切れたとみなす

std::string elmAddress;
NimBLEClient *client = nullptr;
NimBLERemoteCharacteristic *writeChr = nullptr;

// 通知で届いた返事（NimBLE のタスクが足し、ECU のタスクが読む）
portMUX_TYPE replyLock = portMUX_INITIALIZER_UNLOCKED;
char replyBuf[128];
size_t replyLen = 0;
volatile bool replyDone = false;

void onNotify(NimBLERemoteCharacteristic *, uint8_t *data, size_t n, bool) {
  portENTER_CRITICAL(&replyLock);
  for (size_t i = 0; i < n; i++) {
    char c = (char)data[i];
    if (c == '>') {
      replyDone = true;
      continue;
    }
    if (c == '\r' || c == '\n' || c == ',') c = ' ';  // CSV の 1 列に入れるので、改行とカンマを持ち込まない
    if (c == ' ' && (replyLen == 0 || replyBuf[replyLen - 1] == ' ')) continue;
    if (replyLen < sizeof(replyBuf) - 1 && isprint((unsigned char)c)) replyBuf[replyLen++] = c;
  }
  portEXIT_CRITICAL(&replyLock);
}

// 1 つの命令を送り、プロンプト（>）まで待つ。返事は reply に入れる。時間切れなら false
bool transact(const char *cmd, char *reply, size_t size, uint32_t timeoutMs) {
  reply[0] = '\0';
  if (!elm::allowedCommand(cmd)) return false;  // ここで止める（送らない）
  if (!writeChr || !client || !client->isConnected()) return false;
  portENTER_CRITICAL(&replyLock);
  replyLen = 0;
  replyDone = false;
  portEXIT_CRITICAL(&replyLock);
  char line[24];
  int len = snprintf(line, sizeof(line), "%s\r", cmd);
  if (!writeChr->writeValue((const uint8_t *)line, len, false)) return false;
  uint32_t start = millis();
  while (!replyDone && millis() - start < timeoutMs && !stopRequested) vTaskDelay(pdMS_TO_TICKS(1));
  portENTER_CRITICAL(&replyLock);
  size_t n = replyLen < size - 1 ? replyLen : size - 1;
  memcpy(reply, replyBuf, n);
  bool done = replyDone;
  portEXIT_CRITICAL(&replyLock);
  while (n > 0 && reply[n - 1] == ' ') n--;
  reply[n] = '\0';
  return done;
}

// アダプターにつなぎ、返事の通知を受けられるようにする
bool connectAdapter() {
  if (!client->connect(NimBLEAddress(elmAddress, BLE_ADDR_PUBLIC))) return false;
  NimBLERemoteService *svc = client->getService(SERVICE_UUID);
  NimBLERemoteCharacteristic *notifyChr = svc ? svc->getCharacteristic(NOTIFY_UUID) : nullptr;
  writeChr = svc ? svc->getCharacteristic(WRITE_UUID) : nullptr;
  if (!notifyChr || !writeChr || !notifyChr->subscribe(true, onNotify)) {
    client->disconnect();
    writeChr = nullptr;
    return false;
  }
  return true;
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
    if (!connectAdapter() || stopRequested) continue;
    if (!initElm()) {
      client->disconnect();
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
      if (!client->isConnected()) {
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
    if (client->isConnected()) client->disconnect();
    lastTry = millis();
  }
  ecuConnected = false;
  if (client && client->isConnected()) client->disconnect();
  vTaskDelay(pdMS_TO_TICKS(200));
  NimBLEDevice::deinit(true);  // BLE を止めてメモリを空ける（この後 Wi-Fi・HTTPS で送る）
  client = nullptr;
  writeChr = nullptr;
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
  uint8_t bytes[6];
  if (!parseBtAddress(address, bytes)) return false;
  // 空きメモリが足りなければ BLE を始めない（足りないまま始めると落ちることがある）
  uint32_t freeHeap = ESP.getFreeHeap(), largest = ESP.getMaxAllocHeap();
  if (freeHeap < MIN_FREE_HEAP || largest < MIN_LARGEST_BLOCK) {
    char d[48];
    snprintf(d, sizeof(d), "reply=heap %lu largest %lu", (unsigned long)freeHeap, (unsigned long)largest);
    logEvent("ecu_init_ng", d);
    return false;
  }
  elmAddress = std::string(address.c_str());
  NimBLEDevice::init("");
  client = NimBLEDevice::createClient();
  client->setConnectTimeout(5000);
  // つながりの間隔を短くして、返事を早く受け取る（7.5〜15 ms）
  client->setConnectionParams(6, 12, 0, 200);
  ecuStopped = false;
  xTaskCreatePinnedToCore(ecuTask, "ecu", 6144, nullptr, 2, nullptr, 1);
  return true;
}
