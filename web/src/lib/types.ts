// データの型。S3 の app/v1/ に置く JSON の形（docs/data_contract.md と同じ）。
// 作る側は ct125-logger の `python -m ct125 export`（src/ct125/export.py・spectro.py）。

export type GpsKind = "full" | "partial" | "none";
export type HighlightBasis = "z_speed>3" | "z_speed_top" | "score_if_top";
type Num = number | null;

/** rides.json の rides[] の 1 件（走行一覧のカード） */
export interface RideSummary {
  id: string;
  start_ms: number | null; // 記録開始の UNIX ミリ秒。GPS なしは null
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
  spark: Num[]; // rms を 60 区間に平均したもの
  memo: string;
}

export interface RidesFile {
  generated_at_ms: number;
  rides: RideSummary[];
}

/** ride_<id>.json の columns（1 秒窓ごとの列。どれも長さ n） */
export interface RideColumns {
  t_rel: Num[];
  t_abs_ms: Num[] | null; // GPS なしは null
  lat: Num[]; // 自宅周辺・GPS なしは null
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
  cls: number[]; // 地図の色の段階 0〜4（座標のない窓は -1）
  highlight: boolean[];
}

export interface RideData {
  id: string;
  n: number;
  has_abs_time: boolean;
  highlight_basis: HighlightBasis;
  columns: RideColumns;
}

/** spec_<id>.json（spec_<id>.png の説明）。画像は 行＝周波数（上が高い）、列＝窓、不透明度＝強さ */
export interface SpecMeta {
  id: string;
  n_cols: number;
  f_max_hz: number;
  window_sec: number;
  db_min: number;
  db_max: number;
  pct: [number, number];
  peak_hz: Num[]; // 各窓で最も強い周波数（5 Hz 以上）
}

/** wave_<id>.json の windows[] の 1 件（見どころの窓の 1 秒分。平均を引いた mg の整数） */
export interface Waveform {
  i: number; // 窓の添字（ride_<id>.json の列の位置）
  fs: number;
  t0: number;
  ax: number[];
  ay: number[];
  az: number[];
}

export interface WaveFile {
  id: string;
  unit: "mg";
  windows: Waveform[];
}
