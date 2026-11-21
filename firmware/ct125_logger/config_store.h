// 機器の設定（Wi-Fi・機器トークン・送り先）。ESP32 の内部フラッシュ（NVS）に保存する。
// ソースにも SD にも置かない（SD は抜き差しできるので）。書き込みは USB シリアルから（scripts/provision-device.ps1）。
//
// シリアルのコマンド（1 行ずつ。値は画面に出さない）
//   CFG SET <キー> <値>   キー：wifi_ssid wifi_pass wifi2_ssid wifi2_pass device_id device_token api_base ecu_addr auto_upload
//                         ecu_addr は ECU のアダプター（ELM327 互換）の BLE のアドレス（例 AA:BB:CC:12:22:33。Bluetooth Classic のアドレスとは違う。秘密ではない）。
//                         入っていなければ ECU は読まない（V3.8）
//                         auto_upload を off にすると、自動の送信（止まって静か 2 分で記録を閉じて送る・起動時に ADXL345 が
//                         無く 30 秒待っても来ないときに送り残しを送る）をしない。机の上の試し用。手で始める送信（BOOT ボタン・
//                         シリアルの UPLOAD）と送信の手順は変わらない。on か、入れていなければ自動で送る。起動したときに読む（V3.8）
//   CFG STATUS            どのキーが入っているか（値は出さない）
//   CFG CLEAR             全部消す
#pragma once
#include <Arduino.h>

struct DeviceConfig {
  String wifiSsid, wifiPass;    // 送信に使う Wi-Fi（2.4GHz）
  String wifi2Ssid, wifi2Pass;  // 予備（スマホのテザリングなど。無くてよい）
  String deviceId, deviceToken; // register-device で作った機器 ID とトークン
  String apiBase;               // 送り先（既定 https://drive.herdio-system.com）
  String ecuAddr;               // ECU のアダプターの BLE のアドレス（無ければ ECU は読まない）
  bool autoUpload = true;       // 自動の送信（止まって静か 2 分・ADXL を待つ間）をするか。auto_upload が off なら false

  bool hasWifi() const { return wifiSsid.length() > 0 || wifi2Ssid.length() > 0; }
  bool hasDevice() const { return deviceId.length() > 0 && deviceToken.length() > 0; }
};

DeviceConfig loadConfig();

// "CFG ..." の 1 行を処理する。CFG で始まらなければ false
bool handleConfigCommand(const String &line);
