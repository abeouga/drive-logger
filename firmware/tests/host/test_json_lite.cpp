// json_lite.h のテスト（PC で動かす）。CI（.github/workflows/firmware.yml）が g++ でコンパイルして流す。
//   g++ -std=c++17 -I firmware/tests/host -I firmware/ct125_logger firmware/tests/host/test_json_lite.cpp -o /tmp/t && /tmp/t
#include <cstdio>

#include "json_lite.h"

static int failures = 0;

static void expect(bool ok, const char *what) {
  if (!ok) {
    std::printf("NG: %s\n", what);
    failures++;
  }
}

int main() {
  using jsonlite::isUploadableFirmware;
  using jsonlite::jsonString;

  // meta.json は firmware が「"firmware": "..."」と、コロンの後に空白を入れて書く
  const char *metaV32 = "{\n  \"spec\": \"v2\",\n  \"firmware\": \"CT125_LOGGER_V3.2\",\n  \"build\": \"Nov  9 2026\"\n}";
  expect(jsonString(metaV32, "firmware") == "CT125_LOGGER_V3.2", "空白のある meta.json から firmware を読む");
  expect(isUploadableFirmware(metaV32), "V3.2 は送る");
  expect(isUploadableFirmware("{\"firmware\":\"CT125_LOGGER_V3.10\"}"), "空白が無くても読む・V3.10");
  expect(isUploadableFirmware("{ \"firmware\" :\t\"CT125_LOGGER_V4.0\" }"), "コロンの前後の空白とタブ・V4");
  expect(!isUploadableFirmware("{\"firmware\": \"CT125_LOGGER_V2.1\"}"), "V2.1 は送らない");
  expect(!isUploadableFirmware("{\"firmware\": \"OTHER_V3.0\"}"), "違う名前は送らない");
  expect(!isUploadableFirmware("{\"firmware\": \"CT125_LOGGER_Vx\"}"), "版が数でなければ送らない");
  expect(!isUploadableFirmware("{\"spec\": \"v2\"}"), "firmware が無ければ送らない");
  expect(!isUploadableFirmware("{\"firmware\": 3}"), "値が文字列でなければ送らない");
  expect(isUploadableFirmware("{\"note\": \"firmware\", \"firmware\": \"CT125_LOGGER_V3.1\"}"), "値の中の \"firmware\" はキーとみなさず、次を読む");

  // デバイス API の応答（区切りの空白なし）と、エスケープ
  const char *ticket = "{\"ride_id\":\"ride_20261108_011304\",\"expires_in\":900,\"uploads\":[{\"name\":\"accel.csv\",\"url\":\"https:\\/\\/s3\\/a?x=1\"},{\"name\":\"gps.csv\",\"url\":\"https://s3/b\"}],\"status\":\"new\"}";
  expect(jsonString(ticket, "ride_id") == "ride_20261108_011304", "応答から走行 ID を読む");
  int end = 0;
  expect(jsonString(ticket, "name", 0, &end) == "accel.csv", "1 つ目のファイル名");
  expect(jsonString(ticket, "url", end, &end) == "https://s3/a?x=1", "\\/ を / に戻す");
  expect(jsonString(ticket, "name", end, &end) == "gps.csv", "2 つ目のファイル名（続きから読む）");
  expect(jsonString(ticket, "missing") == "", "無いキーは空");

  std::printf(failures ? "%d 件 NG\n" : "すべて OK\n", failures);
  return failures ? 1 : 0;
}
