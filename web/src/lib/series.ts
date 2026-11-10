// 窓の列データを扱う小さな関数（地図とタイムラインで共通）
import type { RideData } from "./data";

export type Selection = number | null; // 窓の番号（配列の添字）

/** 横軸の値：絶対時刻があれば ms、なければ起動からの秒 */
export function xValues(d: RideData): number[] {
  const c = d.columns;
  if (d.has_abs_time && c.t_abs_ms) return c.t_abs_ms.map((v, i) => v ?? (c.t_rel[i] ?? i));
  return c.t_rel.map((v, i) => v ?? i);
}

/** 昇順の xs から v に最も近い添字（二分探索） */
export function nearestIndex(xs: number[], v: number): number {
  let lo = 0;
  let hi = xs.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= v) lo = mid;
    else hi = mid;
  }
  return Math.abs(xs[hi] - v) < Math.abs(xs[lo] - v) ? hi : lo;
}

/** flags が true の連続区間 [始め, 終わり]（添字） */
export function runs(flags: boolean[]): [number, number][] {
  const out: [number, number][] = [];
  let start = -1;
  flags.forEach((f, i) => {
    if (f && start < 0) start = i;
    if (!f && start >= 0) {
      out.push([start, i - 1]);
      start = -1;
    }
  });
  if (start >= 0) out.push([start, flags.length - 1]);
  return out;
}

/** 基準を超えた振動（しきい値を超えた窓）の添字を、スコアの高い順に並べる（並び順＝地図・グラフ・一覧の番号） */
export function rankedAnomalies(d: RideData): number[] {
  const c = d.columns;
  const score = c.anomaly_score;
  return c.anomaly
    .map((h, i) => (h ? i : -1))
    .filter((i) => i >= 0)
    .sort((a, b) => (score[b] ?? -Infinity) - (score[a] ?? -Infinity));
}

export function hasCoord(d: RideData, i: number): boolean {
  return d.columns.lat[i] !== null && d.columns.lon[i] !== null;
}

/** 判定しているか（GPS がなく速度が分からない走行は判定しない） */
export function isJudged(d: RideData): boolean {
  return d.anomaly.method !== "none";
}

/** しきい値の式（例：z_speed > 3）。画面用データの方法としきい値から作る。判定しないときは null */
export function anomalyRuleText(d: RideData): string | null {
  if (d.anomaly.method === "speed_baseline") return `z_speed > ${d.anomaly.threshold ?? "—"}`;
  return null;
}

/** 判定のしかたの説明（画面用データの方法としきい値から作る。モデルを差し替えても文を決め打ちしない） */
export function anomalyBasisText(d: RideData): string {
  const rule = anomalyRuleText(d);
  if (rule) return `速度で補正したベースラインから大きく離れた所（${rule}）を出しています`;
  return "速度が分からないため判定していません";
}

/** 基準を超えた振動が 0 件のときの説明。判定しないときは anomalyBasisText と同じ文になるので null */
export function anomalyEmptyText(d: RideData): string | null {
  const rule = anomalyRuleText(d);
  return rule ? `この走行には、しきい値（${rule}）を超えた所はありません` : null;
}

/** グラフに引くしきい値の線（z_speed の段）。判定しないときは引かない */
export function zThreshold(d: RideData): number | undefined {
  return d.anomaly.method === "speed_baseline" && d.anomaly.threshold !== null ? d.anomaly.threshold : undefined;
}

/** 判定に使ったスコアの短い名前（一覧の右端に添える） */
export const SCORE_LABEL = { speed_baseline: "z", none: "" } as const;
