// データの型。画面用 JSON の形（web/docs/data_contract.md と同じ）。
// 作る側は pipeline/ の export.py・spectro.py。

export type GpsKind = "full" | "partial" | "none";
/**
 * いつもと違う振動の判定の方法。speed_baseline＝速度で補正したベースラインからの逸脱（z_speed）、
 * speed_iforest＝速度を足した Isolation Forest のスコア（score_if）のうち振動が大きい側、none＝判定しない（GPS なし）
 */
export type AnomalyMethod = "speed_baseline" | "speed_iforest" | "none";
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
  n_anomalies: number; // いつもと違う振動の数（判定しない走行は 0。anomaly_method で見分ける）
  anomaly_method: AnomalyMethod;
  n_anomaly_z: number;
  n_anomaly_if: number;
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
  lat: Num[]; // GPS なしは null
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
  is_clipped: boolean[];
  is_anomaly_z: boolean[];
  is_anomaly_if: boolean[];
  cls: number[]; // 地図の色の段階 0〜4（座標のない窓は -1）
  anomaly: boolean[]; // いつもと違う振動の窓（しきい値を超えた窓だけ）
  anomaly_score: Num[]; // 判定に使ったスコア（大きいほど外れ）。判定しない窓は null
}

/** ride_<id>.json の anomaly（判定のしかた。画面は method と columns.anomaly だけを読み、どのモデルかは気にしない） */
export interface AnomalyInfo {
  method: AnomalyMethod;
  threshold: number | null; // 判定しないときは null
  model_version: string | null;
}

export interface RideData {
  id: string;
  n: number;
  has_abs_time: boolean;
  anomaly: AnomalyInfo;
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

/** wave_<id>_<chunk>.json の windows[] の 1 件（1 秒窓の生波形。平均を引いた mg の整数） */
export interface Waveform {
  i: number; // 窓の添字（ride_<id>.json の列の位置）
  fs: number;
  t0: number;
  ax: number[];
  ay: number[];
  az: number[];
}

/** wave_<id>_<chunk>.json（全部の 1 秒窓を、窓の添字 60 個＝約 1 分ごとに分けた 1 ファイル。src/lib/wave.ts） */
export interface WaveFile {
  id: string;
  unit: "mg";
  chunk: number; // ファイルの番号（窓の添字 ÷ 60 の商）
  windows: Waveform[];
}

// ------------------------------------------------------------------ データ API の応答（contracts/api/）

export type RideKind = "desk" | "idle" | "ride" | "ride_nogps";

/** GET /api/rides の rides[] の 1 件（走行の台帳から作る） */
export interface LedgerRide {
  id: string;
  original_name: string | null;
  kind: RideKind | null;
  deleted: boolean;
  deleted_at: string | null;
  published_run: string | null;
  summary: RideSummary | null;
}

export interface RidesResponse {
  rides: LedgerRide[];
}

/** GET /api/rides/{id}/runs の runs[] の 1 件（その走行を処理した記録） */
export interface RunInfo {
  run_id: string;
  action: "process" | "retrain";
  created_at: string;
  finished_at: string | null;
  where: "local" | "lambda";
  commit: string | null;
  model_version: string | null;
  status: "running" | "succeeded" | "failed";
  error: string | null;
  published: boolean;
}

export interface RunsResponse {
  ride_id: string;
  runs: RunInfo[];
}

/** GET /api/models の models[] の 1 件 */
export interface ModelItem {
  version: string;
  created_at: string | null;
  where: "local" | "lambda" | null;
  commit: string | null;
  n_rides: number | null;
  n_windows: number | null;
  has_record: boolean;
}

export interface ModelsResponse {
  current: string | null;
  models: ModelItem[];
}

/** POST /api/rides/{id}/purge の要求（ゴミ箱の走行を完全に削除する。#82） */
export interface PurgeRequest {
  confirm_ride_id: string;
}

/** POST /api/rides/{id}/purge の応答（消したもの。run.json とモデルは残る） */
export interface PurgeResponse {
  ride_id: string;
  purged: true;
  removed: { raw_files: number; result_files: number; runs: string[] };
}

/** GET /api/models/{version}（model.json。contracts/records/model.schema.json）のうち画面で使うところ */
export interface ModelRecord {
  version: string;
  created_at: string;
  where: "local" | "lambda";
  commit: string | null;
  run_id: string | null;
  libraries: Record<string, string>;
  config: Record<string, unknown>;
  train: { rides: { ride_id: string; kind: "idle" | "ride"; n_windows: number }[]; n_windows: number };
  excluded: { ride_id: string; reason: "desk" | "ride_nogps" | "deleted" | "failed" | "unclassified" }[];
  summary: { baseline_bins: number; baseline_n_train: number; n_anomaly_z: number; n_anomaly_if: number; n_anomaly_sif?: number };
  /** Isolation Forest の特徴量としきい値。速度を足す前の版には無い */
  forest?: { features: string[]; quantile: number; threshold: number; n_train: number };
}

/** GET /api/me */
export interface Me {
  username: string;
  groups: string[];
  dataset: string;
}
