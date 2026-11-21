#include "config_store.h"

#include <Preferences.h>

namespace {

const char *NAMESPACE = "ct125";
const char *DEFAULT_API_BASE = "https://drive.herdio-system.com";
const char *KEYS[] = {"wifi_ssid", "wifi_pass", "wifi2_ssid", "wifi2_pass", "device_id", "device_token", "api_base", "ecu_addr", "auto_upload"};

bool isKnownKey(const String &key) {
  for (const char *k : KEYS) {
    if (key == k) return true;
  }
  return false;
}

String readKey(Preferences &prefs, const char *key) { return prefs.getString(key, ""); }

void setKey(const String &key, const String &value) {
  if (!isKnownKey(key)) {
    Serial.printf("CFG ERR unknown_key %s\n", key.c_str());
    return;
  }
  Preferences prefs;
  prefs.begin(NAMESPACE, false);
  bool ok = prefs.putString(key.c_str(), value) == value.length();
  prefs.end();
  // 値は出さない（パスワードとトークンが含まれるため）
  Serial.printf(ok ? "CFG OK %s\n" : "CFG ERR write_failed %s\n", key.c_str());
}

void printStatus() {
  Preferences prefs;
  prefs.begin(NAMESPACE, true);
  for (const char *k : KEYS) {
    Serial.printf("CFG %s=%s\n", k, prefs.isKey(k) ? "set" : "unset");
  }
  prefs.end();
  Serial.println("CFG STATUS_END");
}

void clearAll() {
  Preferences prefs;
  prefs.begin(NAMESPACE, false);
  prefs.clear();
  prefs.end();
  Serial.println("CFG OK cleared");
}

}  // namespace

DeviceConfig loadConfig() {
  Preferences prefs;
  prefs.begin(NAMESPACE, true);
  DeviceConfig cfg;
  cfg.wifiSsid = readKey(prefs, "wifi_ssid");
  cfg.wifiPass = readKey(prefs, "wifi_pass");
  cfg.wifi2Ssid = readKey(prefs, "wifi2_ssid");
  cfg.wifi2Pass = readKey(prefs, "wifi2_pass");
  cfg.deviceId = readKey(prefs, "device_id");
  cfg.deviceToken = readKey(prefs, "device_token");
  cfg.apiBase = readKey(prefs, "api_base");
  cfg.ecuAddr = readKey(prefs, "ecu_addr");
  cfg.autoUpload = readKey(prefs, "auto_upload") != "off";
  prefs.end();
  if (cfg.apiBase.isEmpty()) cfg.apiBase = DEFAULT_API_BASE;
  return cfg;
}

bool handleConfigCommand(const String &line) {
  if (!line.startsWith("CFG ")) return false;
  String rest = line.substring(4);
  rest.trim();
  if (rest == "STATUS") {
    printStatus();
  } else if (rest == "CLEAR") {
    clearAll();
  } else if (rest.startsWith("SET ")) {
    String args = rest.substring(4);
    int space = args.indexOf(' ');
    if (space <= 0) {
      Serial.println("CFG ERR usage: CFG SET <key> <value>");
    } else {
      setKey(args.substring(0, space), args.substring(space + 1));
    }
  } else {
    Serial.println("CFG ERR usage: CFG SET|STATUS|CLEAR");
  }
  return true;
}
