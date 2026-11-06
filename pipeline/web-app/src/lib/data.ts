// python -m ct125 export が src/data/ に書き出す JSON の型と読み込み。
// rides.json は最初から読み、走行ごとの JSON は必要になったときに読む（1 ファイルビルドでも HTML に入る）。
import ridesJson from "../data/rides.json";

export type GpsKind = "full" | "partial" | "none";
export type HighlightBasis = "z_speed>3" | "z_speed_top" | "score_if_top";

export interface RideSummary {
  id: string;
  start_ms: number | null;
  duration_s: number;
  distance_km: number;
  max_speed_kmh: number | null;
  fix_ratio: number;
  gps: GpsKind;
  n_windows: number;
  n_highlights: number;
  highlight_basis: HighlightBasis;
  n_anomaly_z: number;
  n_anomaly_if: number;
  n_private: number;
  n_clipped: number;
  rms_median: number;
  spark: (number | null)[];
  memo: string;
}

type Num = number | null;
export interface RideColumns {
  t_rel: Num[];
  t_abs_ms: Num[] | null;
  lat: Num[];
  lon: Num[];
  speed: Num[];
  rms: Num[];
  log_rms: Num[];
  p2p: Num[];
  crest: Num[];
  z: Num[];
  score_if: Num[];
  band_1_5: Num[];
  band_5_15: Num[];
  band_15_40: Num[];
  has_gps: boolean[];
  is_stopped: boolean[];
  is_edge: boolean[];
  is_private: boolean[];
  is_clipped: boolean[];
  is_anomaly_z: boolean[];
  is_anomaly_if: boolean[];
  cls: number[];
  highlight: boolean[];
}

export interface RideData {
  id: string;
  n: number;
  has_abs_time: boolean;
  highlight_basis: HighlightBasis;
  columns: RideColumns;
}

export const rides: RideSummary[] = (ridesJson as { rides: RideSummary[] }).rides;

const loaders = import.meta.glob<RideData>("../data/ride_*.json", { import: "default" });

export function findRide(id: string): RideSummary | undefined {
  return rides.find((r) => r.id === id);
}

export async function loadRide(id: string): Promise<RideData> {
  const load = loaders[`../data/ride_${id}.json`];
  if (!load) throw new Error(`${id} のデータがありません`);
  return load();
}
