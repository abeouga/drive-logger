#include "uploader.h"

#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <SD.h>
#include <WiFi.h>
#include <time.h>

#include <algorithm>
#include <vector>

#include "json_lite.h"
#include "root_ca.h"

namespace {

// 送るファイル（contracts/upload/upload.json の files.allowed のうち、SD にありうるもの。無いファイルは飛ばす）
// notes.md が走行メモ。memo.txt は古い名前
const char *SEND_FILES[] = {"accel.csv", "gps.csv", "events.csv", "status.csv", "ecu.csv", "meta.json", "notes.md", "memo.txt"};
// この版以降のファームウェアが書いた走行だけを送る（それより前の走行は PC から上げ済み・机上の試験）。
// meta.json の "firmware" の値（例 CT125_LOGGER_V3.2）を JSON として読み、V の後の数（版の上の数）で比べる
// （判定は json_lite.h の isUploadableFirmware。名前と版の数も json_lite.h にある）
// 短すぎる走行（電源を入れてすぐ切った・設定のための再起動）は送らない。約 30 秒分
const size_t MIN_ACCEL_BYTES = 500 * 1024;
const char *UPLOADED_FILE = "uploaded.json";
const char *STATE_FILE = "upload_state.json";
const char *LOG_FILE = "/upload_log.csv";
const uint32_t WIFI_TIMEOUT_MS = 20000;
const uint32_t HTTP_TIMEOUT_MS = 60000;
const int PUT_ATTEMPTS = 3;

struct UploadTarget {
  String name;
  String url;
};

struct Ticket {
  String rideId;
  std::vector<UploadTarget> targets;
};

// ---------------------------------------------------------------- 記録（SD の /upload_log.csv とシリアル）
void logUpload(const String &session, const String &rideId, const char *what, const String &detail) {
  Serial.printf("UPLOAD %s %s %s %s\n", session.c_str(), rideId.c_str(), what, detail.c_str());
  File f = SD.open(LOG_FILE, FILE_APPEND);
  if (!f) return;
  f.printf("%lld,%ld,%s,%s,%s,%s\n", (long long)esp_timer_get_time(), (long)time(nullptr), session.c_str(), rideId.c_str(), what,
           detail.c_str());
  f.close();
}

// ---------------------------------------------------------------- Wi-Fi と時計
bool tryWifi(const String &ssid, const String &pass) {
  if (ssid.isEmpty()) return false;
  WiFi.begin(ssid.c_str(), pass.c_str());
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) delay(250);
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.disconnect(true);
  return false;
}

bool connectWifi(const DeviceConfig &cfg) {
  WiFi.mode(WIFI_STA);
  return tryWifi(cfg.wifiSsid, cfg.wifiPass) || tryWifi(cfg.wifi2Ssid, cfg.wifi2Pass);
}

void disconnectWifi() {
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
}

// 証明書の有効期限を確かめるには正しい時刻が要る
bool syncClock() {
  configTime(0, 0, "ntp.nict.jp", "time.google.com");
  uint32_t start = millis();
  while (time(nullptr) < 1700000000 && millis() - start < 10000) delay(200);
  return time(nullptr) >= 1700000000;
}

// ---------------------------------------------------------------- SD の走行
String sessionPath(const String &session, const char *file) { return "/sessions/" + session + "/" + file; }

String readSmallFile(const String &path) {
  File f = SD.open(path);
  if (!f) return "";
  String text = f.readString();
  f.close();
  return text;
}

bool writeSmallFile(const String &path, const String &text) {
  File f = SD.open(path, FILE_WRITE);
  if (!f) return false;
  size_t written = f.print(text);
  f.close();
  return written == text.length();
}

size_t fileSize(const String &path) {
  File f = SD.open(path);
  if (!f) return 0;
  size_t size = f.size();
  f.close();
  return size;
}

bool isUploadable(const String &session) {
  if (SD.exists(sessionPath(session, UPLOADED_FILE))) return false;
  if (!jsonlite::isUploadableFirmware(readSmallFile(sessionPath(session, "meta.json")))) return false;
  return fileSize(sessionPath(session, "accel.csv")) >= MIN_ACCEL_BYTES;
}

std::vector<String> pendingSessions() {
  std::vector<String> sessions;
  File dir = SD.open("/sessions");
  if (!dir) return sessions;
  for (File entry = dir.openNextFile(); entry; entry = dir.openNextFile()) {
    String name = entry.name();
    bool isDir = entry.isDirectory();
    entry.close();
    if (isDir && isUploadable(name)) sessions.push_back(name);
  }
  dir.close();
  std::sort(sessions.begin(), sessions.end(), [](const String &a, const String &b) { return a < b; });  // ride_NNN の古い順
  return sessions;
}

std::vector<String> filesToSend(const String &session) {
  std::vector<String> files;
  for (const char *name : SEND_FILES) {
    if (SD.exists(sessionPath(session, name))) files.push_back(name);
  }
  return files;
}

// ---------------------------------------------------------------- JSON（形が決まっているので、必要な値だけ取り出す）

bool parseTicket(const String &json, Ticket &ticket) {
  ticket.rideId = jsonlite::jsonString(json, "ride_id");
  ticket.targets.clear();
  int pos = json.indexOf("\"uploads\"");
  while (pos >= 0) {
    int end = 0;
    String name = jsonlite::jsonString(json, "name", pos, &end);
    if (name.isEmpty()) break;
    String url = jsonlite::jsonString(json, "url", end, &end);
    if (url.isEmpty()) return false;
    ticket.targets.push_back({name, url});
    pos = end;
  }
  return ticket.rideId.length() > 0 && !ticket.targets.empty();
}

String uploadRequestBody(const String &session, const std::vector<String> &files, const String &resumeRideId) {
  String body = "{\"local_session\":\"" + session + "\",\"files\":[";
  for (size_t i = 0; i < files.size(); i++) {
    if (i) body += ",";
    body += "{\"name\":\"" + files[i] + "\",\"size\":" + String((unsigned long)fileSize(sessionPath(session, files[i].c_str()))) + "}";
  }
  body += "]";
  if (resumeRideId.length()) body += ",\"ride_id\":\"" + resumeRideId + "\"";
  body += "}";
  return body;
}

// ---------------------------------------------------------------- HTTPS
int postJson(const DeviceConfig &cfg, const String &path, const String &body, String &response) {
  NetworkClientSecure client;
  client.setCACert(ROOT_CA_PEM);
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(client, cfg.apiBase + path)) return -1;
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Device " + cfg.deviceId + "." + cfg.deviceToken);
  int code = http.POST(body);
  response = code > 0 ? http.getString() : "";
  http.end();
  return code;
}

int putFile(const String &url, const String &path) {
  File f = SD.open(path);
  if (!f) return -1;
  NetworkClientSecure client;
  client.setCACert(ROOT_CA_PEM);
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  int code = -1;
  if (http.begin(client, url)) {
    code = http.sendRequest("PUT", &f, f.size());  // SD から流しながら送る（全部をメモリに載せない）
    http.end();
  }
  f.close();
  return code;
}

// ---------------------------------------------------------------- 1 走行
enum class SessionResult { Sent, Aborted, Failed };

int requestTicket(const DeviceConfig &cfg, const String &session, const String &resumeRideId, Ticket &ticket) {
  String response;
  int code = postJson(cfg, "/api/device/uploads", uploadRequestBody(session, filesToSend(session), resumeRideId), response);
  if (code == 200 && !parseTicket(response, ticket)) return -2;
  if (code != 200) logUpload(session, resumeRideId, "ticket_error", String(code) + " " + response.substring(0, 120));
  return code;
}

void markUploaded(const String &session, const String &rideId) {
  writeSmallFile(sessionPath(session, UPLOADED_FILE), "{\"ride_id\":\"" + rideId + "\",\"uploaded_at\":" + String((long)time(nullptr)) + "}\n");
  SD.remove(sessionPath(session, STATE_FILE));
}

// ファイルを 1 つ送る。失敗したら少し待って PUT_ATTEMPTS 回まで。返り値は最後の HTTP ステータス
int putWithRetry(const String &url, const String &path) {
  int code = -1;
  for (int attempt = 1; attempt <= PUT_ATTEMPTS; attempt++) {
    code = putFile(url, path);
    if (code == 200 || code == 403) return code;  // 403 は URL の期限切れ。やり直しても同じなので呼び出し元に任せる
    delay(2000 * attempt);
  }
  return code;
}

bool sendFiles(const DeviceConfig &cfg, const String &session, Ticket &ticket, bool (*shouldAbort)(), bool &aborted) {
  bool refreshed = false;  // URL の出し直しは 1 回だけ
  for (size_t i = 0; i < ticket.targets.size(); i++) {
    if (shouldAbort()) {
      aborted = true;
      return false;
    }
    const UploadTarget &target = ticket.targets[i];
    int code = putWithRetry(target.url, sessionPath(session, target.name.c_str()));
    if (code == 403 && !refreshed) {  // 期限切れ：同じ走行名で URL を出し直してもらい、このファイルからやり直す
      Ticket fresh;
      if (requestTicket(cfg, session, ticket.rideId, fresh) != 200) return false;
      ticket = fresh;
      refreshed = true;
      i--;
      continue;
    }
    logUpload(session, ticket.rideId, code == 200 ? "put_ok" : "put_error", target.name + " " + String(code));
    if (code != 200) return false;
  }
  return true;
}

SessionResult uploadSession(const DeviceConfig &cfg, const String &session, bool (*shouldAbort)()) {
  String resumeRideId = jsonlite::jsonString(readSmallFile(sessionPath(session, STATE_FILE)), "ride_id");
  Ticket ticket;
  int code = requestTicket(cfg, session, resumeRideId, ticket);
  if (code == 409 && resumeRideId.length()) {  // 前回、完了まで届いていた
    markUploaded(session, resumeRideId);
    return SessionResult::Sent;
  }
  if (code == 404 && resumeRideId.length()) {  // 前回の受け付けが無い：最初から
    SD.remove(sessionPath(session, STATE_FILE));
    code = requestTicket(cfg, session, "", ticket);
  }
  if (code != 200) return SessionResult::Failed;
  writeSmallFile(sessionPath(session, STATE_FILE), "{\"ride_id\":\"" + ticket.rideId + "\"}\n");
  logUpload(session, ticket.rideId, "ticket", String(ticket.targets.size()) + " files");

  bool aborted = false;
  if (!sendFiles(cfg, session, ticket, shouldAbort, aborted)) {
    if (aborted) logUpload(session, ticket.rideId, "aborted", "moving");
    return aborted ? SessionResult::Aborted : SessionResult::Failed;
  }

  String response;
  code = postJson(cfg, "/api/device/uploads/" + ticket.rideId + "/complete", "{}", response);
  logUpload(session, ticket.rideId, code == 200 ? "complete" : "complete_error", String(code) + " " + response.substring(0, 120));
  if (code != 200) return SessionResult::Failed;
  markUploaded(session, ticket.rideId);
  return SessionResult::Sent;
}

}  // namespace

const char *uploadResultName(UploadResult result) {
  switch (result) {
    case UploadResult::Done: return "done";
    case UploadResult::NothingToSend: return "nothing_to_send";
    case UploadResult::NoConfig: return "no_config";
    case UploadResult::NoWifi: return "no_wifi";
    case UploadResult::Aborted: return "aborted";
    default: return "failed";
  }
}

UploadSummary uploadPendingSessions(const DeviceConfig &cfg, bool (*shouldAbort)()) {
  UploadSummary summary{UploadResult::NothingToSend, 0, 0};
  if (!cfg.hasWifi() || !cfg.hasDevice()) {
    summary.result = UploadResult::NoConfig;
    return summary;
  }
  std::vector<String> sessions = pendingSessions();
  if (sessions.empty()) return summary;
  if (!connectWifi(cfg)) {
    summary.result = UploadResult::NoWifi;
    return summary;
  }
  if (!syncClock()) logUpload("-", "-", "clock_warning", "ntp_failed");
  for (const String &session : sessions) {
    SessionResult result = uploadSession(cfg, session, shouldAbort);
    if (result == SessionResult::Sent) summary.sent++;
    if (result == SessionResult::Failed) summary.failed++;
    if (result == SessionResult::Aborted) {
      summary.result = UploadResult::Aborted;
      disconnectWifi();
      return summary;
    }
  }
  disconnectWifi();
  summary.result = summary.failed ? UploadResult::Failed : UploadResult::Done;
  return summary;
}
