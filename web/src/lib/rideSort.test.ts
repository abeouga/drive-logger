import { describe, expect, it } from "vitest";
import type { RideSummary } from "./types";
import { listHashWithSort, rideIdToMs, sortFromHash, sortRides } from "./rideSort";

function ride(id: string, over: Partial<RideSummary> = {}): RideSummary {
  return {
    id,
    name: id,
    start_ms: null,
    duration_s: 600,
    distance_km: 0,
    max_speed_kmh: null,
    fix_ratio: 0,
    gps: "none",
    n_windows: 600,
    n_anomalies: 0,
    anomaly_method: "none",
    n_anomaly_z: 0,
    n_anomaly_if: 0,
    n_clipped: 0,
    rms_median: 0,
    spark: [],
    memo: "",
    ...over,
  };
}

const ms = (iso: string) => Date.parse(iso);

// 記録の日時が分かる走行（GPS あり）と、分からない走行（GPS なし。走行 ID の届いた日時で代える）を混ぜる
const rides = [
  ride("ride_20261109_030100", { start_ms: ms("2026-11-02T13:42:00+09:00"), gps: "partial", distance_km: 0.0, duration_s: 120, n_anomalies: 0, anomaly_method: "speed_baseline" }),
  ride("ride_20261109_030109", { start_ms: ms("2026-11-02T14:03:00+09:00"), gps: "partial", distance_km: 4.8, duration_s: 840, n_anomalies: 2, anomaly_method: "speed_iforest" }),
  ride("ride_20261109_030119", { start_ms: ms("2026-11-02T14:52:00+09:00"), gps: "full", distance_km: 4.3, duration_s: 900, n_anomalies: 2, anomaly_method: "speed_baseline" }),
  ride("ride_20261109_030139", { duration_s: 2220 }), // GPS なし（判定しない）。届いたのは 11/9 3:01 JST
  ride("ride_20261101_120000", { duration_s: 60 }), // GPS なし（判定しない）。届いたのは 11/1 12:00 JST
];
const ids = (list: RideSummary[]) => list.map((r) => r.id.slice(5));

describe("rideIdToMs", () => {
  it("走行 ID の日時を日本時間として読む", () => {
    expect(rideIdToMs("ride_20261109_030206")).toBe(ms("2026-11-09T03:02:06+09:00"));
    expect(rideIdToMs("ride_20261109_030206_2")).toBe(ms("2026-11-09T03:02:06+09:00"));
  });
  it("形の違う ID は null", () => {
    expect(rideIdToMs("ride_009")).toBeNull();
  });
});

describe("sortRides", () => {
  it("新しい順：記録の日時、無ければ届いた日時で並べる", () => {
    expect(ids(sortRides(rides, "new"))).toEqual([
      "20261109_030139",
      "20261109_030119",
      "20261109_030109",
      "20261109_030100",
      "20261101_120000",
    ]);
  });
  it("古い順：新しい順の逆", () => {
    expect(ids(sortRides(rides, "old"))).toEqual(ids(sortRides(rides, "new")).reverse());
  });
  it("距離の長い順：GPS なしの走行は最後（その中は新しい順）", () => {
    expect(ids(sortRides(rides, "distance"))).toEqual([
      "20261109_030109",
      "20261109_030119",
      "20261109_030100",
      "20261109_030139",
      "20261101_120000",
    ]);
  });
  it("時間の長い順", () => {
    expect(ids(sortRides(rides, "duration"))).toEqual([
      "20261109_030139",
      "20261109_030119",
      "20261109_030109",
      "20261109_030100",
      "20261101_120000",
    ]);
  });
  it("基準を超えた振動の多い順：同じ数なら新しい順。判定していない走行は 0 件の後（その中は新しい順）", () => {
    expect(ids(sortRides(rides, "anomalies"))).toEqual([
      "20261109_030119",
      "20261109_030109",
      "20261109_030100",
      "20261109_030139",
      "20261101_120000",
    ]);
  });
  it("基準を超えた振動の多い順：判定していない走行は数が入っていても最後", () => {
    const list = [
      ride("ride_20261109_000000", { n_anomalies: 5 }),
      ride("ride_20261108_000000", { n_anomalies: 0, anomaly_method: "speed_baseline", gps: "full" }),
    ];
    expect(ids(sortRides(list, "anomalies"))).toEqual(["20261108_000000", "20261109_000000"]);
  });
  it("どの並べ方でも走行が抜けず、元の配列を変えない", () => {
    const before = ids(rides);
    for (const key of ["new", "old", "distance", "duration", "anomalies"] as const) {
      expect(sortRides(rides, key)).toHaveLength(rides.length);
    }
    expect(ids(rides)).toEqual(before);
  });
});

describe("ハッシュの並べ方", () => {
  it("?sort= を読み書きする", () => {
    expect(sortFromHash("#/?sort=distance")).toBe("distance");
    expect(sortFromHash(listHashWithSort("anomalies"))).toBe("anomalies");
    expect(listHashWithSort("new")).toBe("#/");
  });
  it("無い・知らない値は null", () => {
    expect(sortFromHash("#/")).toBeNull();
    expect(sortFromHash("#/?sort=nope")).toBeNull();
  });
  it("前の値（sort=highlights）は既定の並べ方に読み替える", () => {
    expect(sortFromHash("#/?sort=highlights")).toBe("new");
  });
});
