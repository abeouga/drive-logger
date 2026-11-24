// 窓の列データを扱う小さな関数（地図とタイムラインで共通）
import type { AnomalyMethod, RideColumns, RideData } from "./data";

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

/** 判定の方法ごとの、スコアの名前と説明（方法の名前は画面用データから選ぶ） */
const METHOD_RULE: Record<Exclude<AnomalyMethod, "none">, { score: string; basis: string }> = {
  speed_baseline: { score: "z_speed", basis: "速度で補正したベースラインから大きく離れた所" },
  speed_iforest: { score: "score_if", basis: "速度と振動の特徴量で学習した Isolation Forest で、まれな組み合わせのうち振動がふだんより大きい所" },
};

/** しきい値の式（例：z_speed > 3）。画面用データの方法としきい値から作る。判定しないときは null */
export function anomalyRuleText(d: RideData): string | null {
  if (d.anomaly.method === "none") return null;
  const rule = METHOD_RULE[d.anomaly.method];
  return rule ? `${rule.score} > ${d.anomaly.threshold ?? "—"}` : null;
}

/** 判定のしかたの説明（画面用データの方法としきい値から作る。モデルを差し替えても文を決め打ちしない） */
export function anomalyBasisText(d: RideData): string {
  const rule = anomalyRuleText(d);
  if (rule && d.anomaly.method !== "none") return `${METHOD_RULE[d.anomaly.method].basis}（${rule}）を出しています`;
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

/** グラフに引くしきい値の線（score_if の段）。speed_iforest で判定したときだけ */
export function scoreIfThreshold(d: RideData): number | undefined {
  return d.anomaly.method === "speed_iforest" && d.anomaly.threshold !== null ? d.anomaly.threshold : undefined;
}

/** 判定に使ったスコアの短い名前（一覧の右端に添える） */
export const SCORE_LABEL: Record<AnomalyMethod, string> = { speed_baseline: "z", speed_iforest: "score", none: "" };

/** ECU の値の列（#143）。版 3 までの JSON には無いので、無ければ null で埋める */
export type EcuKey = Extract<keyof RideColumns, `ecu_${string}`>;

export function ecuValues(d: RideData, key: EcuKey): (number | null)[] {
  return d.columns[key] ?? d.columns.t_rel.map(() => null);
}

/** 窓ごとに ECU の値があるか。列が無い JSON（#143 より前に処理した走行）は全部 false */
export function ecuFlags(d: RideData): boolean[] {
  return d.columns.has_ecu ?? d.columns.t_rel.map(() => false);
}

/** この走行に ECU の値がある窓が 1 つでもあるか（タイムラインに回転数の段を出すか） */
export function hasEcu(d: RideData): boolean {
  return ecuFlags(d).some(Boolean);
}
