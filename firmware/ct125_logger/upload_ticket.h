#pragma once
// デバイス API の受け付け（POST /api/device/uploads）の応答の読み取り（contracts/upload/start_response.schema.json）。
// Arduino の String だけに頼るので、PC でもテストできる（firmware/tests/host/test_upload_ticket.cpp）。
#include <Arduino.h>

#include <vector>

#include "json_lite.h"

struct UploadTarget {
  String name;
  String url;
};

struct Ticket {
  String rideId;
  // new・resumed・memo_added：targets に送る。already_uploaded：同じ SD の走行を送り終えている（targets は空。#135）
  String status;
  std::vector<UploadTarget> targets;

  bool alreadyUploaded() const { return status == "already_uploaded"; }
};

// 読めれば true。走行 ID は必須。already_uploaded のときだけ、送る先が無くてよい
inline bool parseTicket(const String &json, Ticket &ticket) {
  ticket.rideId = jsonlite::jsonString(json, "ride_id");
  ticket.status = jsonlite::jsonString(json, "status");
  ticket.targets.clear();
  int pos = json.indexOf("\"uploads\"");
  while (pos >= 0) {
    int end = 0;
    String name = jsonlite::jsonString(json, "name", pos, &end);
    if (name.length() == 0) break;
    String url = jsonlite::jsonString(json, "url", end, &end);
    if (url.length() == 0) return false;
    ticket.targets.push_back({name, url});
    pos = end;
  }
  if (ticket.rideId.length() == 0) return false;
  return ticket.alreadyUploaded() || !ticket.targets.empty();
}
