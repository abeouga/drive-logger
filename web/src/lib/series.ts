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

/** 見どころの窓の添字を、スコアの高い順に並べる（順位＝地図とグラフの番号） */
export function rankedHighlights(d: RideData): number[] {
  const c = d.columns;
  const score = d.highlight_basis === "score_if_top" ? c.score_if : c.z;
  return c.highlight
    .map((h, i) => (h ? i : -1))
    .filter((i) => i >= 0)
    .sort((a, b) => (score[b] ?? -Infinity) - (score[a] ?? -Infinity));
}

export function hasCoord(d: RideData, i: number): boolean {
  return d.columns.lat[i] !== null && d.columns.lon[i] !== null;
}

export const BASIS_TEXT = {
  "z_speed>3": "速度で補正したベースラインから 3 MAD 以上離れた窓（z_speed > 3）",
  z_speed_top: "z_speed > 3 の窓はないため、走行中（5 km/h 以上）の z_speed 上位 10 窓を示しています",
  score_if_top: "GPS がなく速度で補正できないため、Isolation Forest のスコア上位 10 窓を示しています（振動が大きすぎる窓だけでなく、静かすぎる窓もまれな窓として上位に入ります）",
} as const;
