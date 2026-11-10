// 走行一覧の並べ方。並べ替えは画面の中だけで行い、API は変えない。
// 選んだ並べ方は URL のハッシュ（#/?sort=…）に持ち、走行の画面から戻っても保つ。
import type { RideSummary } from "./types";

export type RideSortKey = "new" | "old" | "distance" | "duration" | "anomalies";

export const DEFAULT_RIDE_SORT: RideSortKey = "new";

export const RIDE_SORT_OPTIONS: { value: RideSortKey; label: string }[] = [
  { value: "new", label: "新しい順" },
  { value: "old", label: "古い順" },
  { value: "distance", label: "距離の長い順" },
  { value: "duration", label: "時間の長い順" },
  { value: "anomalies", label: "基準を超えた振動の多い順" },
];

const SORT_KEYS = new Set<string>(RIDE_SORT_OPTIONS.map((o) => o.value));

export function isRideSortKey(v: string | null | undefined): v is RideSortKey {
  return v != null && SORT_KEYS.has(v);
}

const JST_OFFSET_MS = 9 * 60 * 60 * 1000;

/** 走行 ID（ride_YYYYMMDD_HHMMSS[_n]。届いた日時・日本時間）を UNIX ミリ秒にする。形が違えば null */
export function rideIdToMs(id: string): number | null {
  const m = id.match(/^ride_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (!m) return null;
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  return Date.UTC(y, mo - 1, d, h, mi, s) - JST_OFFSET_MS;
}

/** 並べるときの日時：記録の日時。分からない走行（GPS なし）は走行 ID（届いた日時）で代える */
export function rideTimeMs(r: RideSummary): number | null {
  return r.start_ms ?? rideIdToMs(r.id);
}

/** 新しい順。日時の分からない走行は最後。日時が同じなら走行 ID の新しい順 */
function byNewest(a: RideSummary, b: RideSummary): number {
  const ta = rideTimeMs(a);
  const tb = rideTimeMs(b);
  if (ta !== tb) {
    if (ta === null) return 1;
    if (tb === null) return -1;
    return tb - ta;
  }
  return b.id.localeCompare(a.id);
}

/** 大きい順。同じなら新しい順 */
const byDesc = (value: (r: RideSummary) => number) => (a: RideSummary, b: RideSummary) =>
  value(b) - value(a) || byNewest(a, b);

/** 基準を超えた振動を判定した走行か。GPS なしの走行は判定しない（anomaly_method が "none"） */
export function isJudged(r: RideSummary): boolean {
  return r.anomaly_method !== "none";
}

export function sortRides(rides: readonly RideSummary[], key: RideSortKey): RideSummary[] {
  const list = [...rides];
  switch (key) {
    case "new":
      return list.sort(byNewest);
    case "old":
      return list.sort(byNewest).reverse();
    case "distance": {
      // GPS なしの走行は距離が分からないので最後（その中は新しい順）
      const withGps = list.filter((r) => r.gps !== "none").sort(byDesc((r) => r.distance_km));
      const noGps = list.filter((r) => r.gps === "none").sort(byNewest);
      return [...withGps, ...noGps];
    }
    case "duration":
      return list.sort(byDesc((r) => r.duration_s));
    case "anomalies": {
      // 判定していない走行（GPS なし）は 0 件と混ぜず最後（その中は新しい順）
      const judged = list.filter(isJudged).sort(byDesc((r) => r.n_anomalies));
      const notJudged = list.filter((r) => !isJudged(r)).sort(byNewest);
      return [...judged, ...notJudged];
    }
  }
}

/** 前に使っていて今は無い並べ方の値。残っているリンクから来たときは既定の並べ方で出す */
const RETIRED_SORT_KEYS = new Set(["highlights"]);

/** ハッシュ（#/?sort=distance など）から並べ方を読む。無い・知らない値なら null。前の値（highlights）は既定の並べ方 */
export function sortFromHash(hash: string): RideSortKey | null {
  const q = hash.indexOf("?");
  if (q < 0) return null;
  const v = new URLSearchParams(hash.slice(q + 1)).get("sort");
  if (v !== null && RETIRED_SORT_KEYS.has(v)) return DEFAULT_RIDE_SORT;
  return isRideSortKey(v) ? v : null;
}

/** 一覧のハッシュ。既定の並べ方なら ?sort= を付けない */
export function listHashWithSort(key: RideSortKey): string {
  return key === DEFAULT_RIDE_SORT ? "#/" : `#/?sort=${key}`;
}
