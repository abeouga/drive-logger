import { describe, expect, it } from "vitest";
import type { AnomalyInfo, RideData } from "./types";
import { SCORE_LABEL, anomalyBasisText, anomalyEmptyText, ecuFlags, ecuValues, hasEcu, isJudged, rankedAnomalies, scoreIfThreshold, zThreshold } from "./series";

// 判定に関わる列だけを持つ走行（ほかの列はこの関数たちが読まないので空にしておく）
function ride(anomaly: boolean[], score: (number | null)[], info: Partial<AnomalyInfo> = {}): RideData {
  return {
    id: "ride_test",
    n: anomaly.length,
    has_abs_time: false,
    anomaly: { method: "speed_baseline", threshold: 3, model_version: null, ...info },
    columns: { anomaly, anomaly_score: score } as unknown as RideData["columns"],
  };
}

describe("rankedAnomalies", () => {
  it("しきい値を超えた窓だけを、スコアの高い順に並べる", () => {
    const d = ride([false, true, true, false, true], [9, 3.5, 7.2, 8, 4.1]);
    // 3 番（score 8）は超えていないので入らない
    expect(rankedAnomalies(d)).toEqual([2, 4, 1]);
  });

  it("超えた所が無ければ空", () => {
    expect(rankedAnomalies(ride([false, false], [2.9, 1]))).toEqual([]);
  });
});

describe("判定の説明", () => {
  it("しきい値を画面用データから取る（決め打ちしない）", () => {
    const d = ride([false], [1], { threshold: 4.5 });
    expect(anomalyBasisText(d)).toContain("z_speed > 4.5");
    expect(anomalyEmptyText(d)).toBe("この走行には、しきい値（z_speed > 4.5）を超えた所はありません");
    expect(zThreshold(d)).toBe(4.5);
    expect(isJudged(d)).toBe(true);
  });

  it("速度を足した Isolation Forest の判定は、score_if としきい値をデータから出す", () => {
    const d = ride([false], [0.01], { method: "speed_iforest", threshold: 0.0781 });
    expect(anomalyBasisText(d)).toContain("Isolation Forest");
    expect(anomalyBasisText(d)).toContain("score_if > 0.0781");
    expect(anomalyEmptyText(d)).toBe("この走行には、しきい値（score_if > 0.0781）を超えた所はありません");
    expect(scoreIfThreshold(d)).toBe(0.0781);
    expect(zThreshold(d)).toBeUndefined();
    expect(isJudged(d)).toBe(true);
    expect(SCORE_LABEL[d.anomaly.method]).toBe("score");
  });

  it("判定していない走行（GPS なし）", () => {
    const d = ride([false], [null], { method: "none", threshold: null });
    expect(isJudged(d)).toBe(false);
    expect(anomalyBasisText(d)).toBe("速度が分からないため判定していません");
    expect(anomalyEmptyText(d)).toBeNull();
    expect(zThreshold(d)).toBeUndefined();
    expect(scoreIfThreshold(d)).toBeUndefined();
  });
});

// ECU の値（#143）：版 3 までの JSON には ECU の列が無い
function ecuRide(columns: Partial<RideData["columns"]>): RideData {
  return {
    id: "ride_test",
    n: 3,
    has_abs_time: false,
    anomaly: { method: "none", threshold: null, model_version: null },
    columns: { t_rel: [0.5, 1.5, 2.5], ...columns } as unknown as RideData["columns"],
  };
}

describe("ECU の値", () => {
  it("ECU の列が無い古い JSON は、全部の窓を ECU なしとして扱う", () => {
    const d = ecuRide({});
    expect(hasEcu(d)).toBe(false);
    expect(ecuFlags(d)).toEqual([false, false, false]);
    expect(ecuValues(d, "ecu_rpm")).toEqual([null, null, null]);
  });

  it("ECU の列がある JSON は、そのまま読む", () => {
    const d = ecuRide({ has_ecu: [false, true, true], ecu_rpm: [null, 1630, 1642] });
    expect(hasEcu(d)).toBe(true);
    expect(ecuFlags(d)).toEqual([false, true, true]);
    expect(ecuValues(d, "ecu_rpm")).toEqual([null, 1630, 1642]);
  });

  it("ECU の無い走行（has_ecu が全部 false）は、回転数の段を出さない", () => {
    expect(hasEcu(ecuRide({ has_ecu: [false, false, false] }))).toBe(false);
  });
});
