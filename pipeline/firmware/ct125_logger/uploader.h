// SD の走行を、Wi-Fi で S3 に送る（C）。手順は ct125-logger/tools/device_upload_simulator.py と同じ：
//   1. POST <api>/api/device/uploads           送るファイルと大きさ → 走行名とファイルごとの PUT 用 URL（15 分）
//   2. 各 URL に HTTP PUT                       SD から流しながら送る
//   3. POST <api>/api/device/uploads/<走行名>/complete  サーバーが大きさを確かめ、AWS の自動処理が始まる
// 送り終えた走行には uploaded.json を書き、次からは送らない。途中で切れたら upload_state.json の走行名でやり直す。
// 記録と同時には動かさない（記録を閉じてから呼ぶ）。
#pragma once
#include <Arduino.h>

#include "config_store.h"

enum class UploadResult {
  Done,           // 送るべき走行をすべて送った（1 件以上）
  NothingToSend,  // 送るべき走行が無かった
  NoConfig,       // Wi-Fi か機器トークンが設定されていない
  NoWifi,         // 知っている Wi-Fi が見つからない・つながらない
  Aborted,        // 動き出したので途中でやめた（次に止まったときに続きから送る）
  Failed,         // 送信やサーバーの確認に失敗した
};

struct UploadSummary {
  UploadResult result;
  int sent;
  int failed;
};

// 送信済みでない走行を古い順に送る。shouldAbort() が true を返したら、ファイルの合間でやめる
UploadSummary uploadPendingSessions(const DeviceConfig &cfg, bool (*shouldAbort)());

const char *uploadResultName(UploadResult result);
