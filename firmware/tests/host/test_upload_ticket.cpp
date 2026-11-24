// upload_ticket.h のテスト（PC で動かす）。CI（.github/workflows/firmware.yml）が g++ でコンパイルして流す。
//   g++ -std=c++17 -I firmware/tests/host -I firmware/ct125_logger firmware/tests/host/test_upload_ticket.cpp -o /tmp/t && /tmp/t
#include <cstdio>

#include "upload_ticket.h"

static int failures = 0;

static void expect(bool ok, const char *what) {
  if (!ok) {
    std::printf("NG: %s\n", what);
    failures++;
  }
}

int main() {
  Ticket ticket;

  const char *fresh = "{\"ride_id\":\"ride_20261108_011304\",\"expires_in\":900,\"uploads\":[{\"name\":\"accel.csv\",\"url\":\"https:\\/\\/s3\\/a\"},{\"name\":\"gps.csv\",\"url\":\"https://s3/b\"}],\"status\":\"new\"}";
  expect(parseTicket(fresh, ticket), "新しい受け付けを読む");
  expect(ticket.rideId == "ride_20261108_011304" && ticket.status == "new", "走行 ID と status");
  expect(ticket.targets.size() == 2 && ticket.targets[1].name == "gps.csv" && ticket.targets[0].url == "https://s3/a", "送る先 2 つ");
  expect(!ticket.alreadyUploaded(), "new は送り終えていない");

  // ほかの経路で送り終えていた（#135）：送る先は空でも読めて、返ってきた走行 ID を使う
  const char *done = "{\"ride_id\":\"ride_20261122_190000\",\"expires_in\":900,\"uploads\":[],\"status\":\"already_uploaded\"}";
  expect(parseTicket(done, ticket), "already_uploaded は送る先が空でも読める");
  expect(ticket.alreadyUploaded() && ticket.rideId == "ride_20261122_190000" && ticket.targets.empty(), "already_uploaded の中身");

  // 送る先が空なのに already_uploaded でなければ、読めないとする（前の版と同じ）
  expect(!parseTicket("{\"ride_id\":\"ride_20261108_011304\",\"expires_in\":900,\"uploads\":[],\"status\":\"new\"}", ticket), "new で送る先が空は読めない");
  expect(!parseTicket("{\"ride_id\":\"ride_20261108_011304\",\"uploads\":[]}", ticket), "status が無く送る先が空は読めない");
  expect(!parseTicket("{\"expires_in\":900,\"uploads\":[],\"status\":\"already_uploaded\"}", ticket), "走行 ID が無ければ読めない");
  expect(!parseTicket("{\"ride_id\":\"ride_20261108_011304\",\"uploads\":[{\"name\":\"accel.csv\"}],\"status\":\"new\"}", ticket), "URL が無い送る先は読めない");

  const char *memo = "{\"ride_id\":\"ride_20261108_011304\",\"expires_in\":900,\"uploads\":[{\"name\":\"notes.md\",\"url\":\"https://s3/n\"}],\"status\":\"memo_added\"}";
  expect(parseTicket(memo, ticket) && ticket.status == "memo_added" && ticket.targets.size() == 1, "memo_added はメモの分だけ送る");

  if (failures) {
    std::printf("%d 件 NG\n", failures);
    return 1;
  }
  std::printf("すべて OK\n");
  return 0;
}
