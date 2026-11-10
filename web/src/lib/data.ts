// 画面が使うデータの読み込みと書き換え。どれもデータ API（src/lib/dataSource.ts）を通す。
//   走行の一覧      ：GET /api/rides（走行の台帳から作る）
//   1 走行のデータ  ：GET /api/data/ride_<id>.json・spec_<id>.png など（公開用のデータ）
//   消す・戻す・完全に削除・切り替え：admin だけ（API も admin かどうかを確かめる）
import { useCallback, useEffect, useState } from "react";
import { DataError, apiFetch, apiJson, fetchDataFile } from "./dataSource";
import { waveFileName } from "./wave";
import type { LedgerRide, ModelRecord, ModelsResponse, PurgeRequest, PurgeResponse, RideData, RideSummary, RidesResponse, RunsResponse, SpecMeta, Waveform, WaveFile } from "./types";

export type * from "./types";
export { DataError };

const SAFE_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;
const RIDE_ID = /^ride_[0-9A-Za-z_]+$/;

function checkName(name: string): void {
  if (!SAFE_NAME.test(name)) throw new DataError(`ファイル名が不正です：${name}`);
}

function checkRideId(id: string): string {
  if (!RIDE_ID.test(id)) throw new DataError(`走行 ID が不正です：${id}`);
  return id;
}

async function getJson<T>(name: string): Promise<T> {
  checkName(name);
  return (await (await fetchDataFile(name)).json()) as T;
}

// 画像の URL。ログインが要るので <img src> に直接書けず、取ってきた中身から URL を作る
const imageUrlCache = new Map<string, Promise<string>>();

async function getImageUrl(name: string): Promise<string> {
  checkName(name);
  let url = imageUrlCache.get(name);
  if (!url) {
    url = fetchDataFile(name).then(async (response) => URL.createObjectURL(await response.blob()));
    imageUrlCache.set(name, url);
  }
  return url;
}

// ------------------------------------------------------------------ 走行の一覧（台帳）
let ridesPromise: Promise<LedgerRide[]> | null = null;
const listeners = new Set<() => void>();

function loadLedger(): Promise<LedgerRide[]> {
  ridesPromise ??= apiJson<RidesResponse>("rides")
    .then((r) => r.rides)
    .catch((e) => {
      ridesPromise = null; // 次に開いたときにやり直せるように
      throw e;
    });
  return ridesPromise;
}

/** 一覧を読み直させる（消す・戻すの後）。開いている画面も読み直す。 */
export function invalidateRides(): void {
  ridesPromise = null;
  listeners.forEach((listener) => listener());
}

/** 画面に出す走行の要約（台帳の公開中の結果）。 */
export function useRides(): { rides: RideSummary[] | null; ledger: LedgerRide[] | null; error: string | null } {
  const [ledger, setLedger] = useState<LedgerRide[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const listener = () => setVersion((v) => v + 1);
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);
  useEffect(() => {
    let alive = true;
    loadLedger().then(
      (r) => alive && (setLedger(r), setError(null)),
      (e: Error) => alive && setError(e.message),
    );
    return () => {
      alive = false;
    };
  }, [version]);
  const rides = ledger ? ledger.flatMap((r) => (r.summary ? [r.summary] : [])) : null;
  return { rides, ledger, error };
}

/** admin：消した走行・机上の走行も入れた台帳。 */
export function loadFullLedger(): Promise<LedgerRide[]> {
  return apiJson<RidesResponse>("rides?include_deleted=true").then((r) => r.rides);
}

export async function deleteRide(id: string): Promise<void> {
  await apiFetch(`rides/${checkRideId(id)}`, { method: "DELETE" });
  invalidateRides();
}

export async function restoreRide(id: string): Promise<void> {
  await apiFetch(`rides/${checkRideId(id)}/restore`, { method: "POST" });
  invalidateRides();
}

/** admin：ゴミ箱の走行を完全に削除する（#82。元に戻せない）。confirmRideId は確かめの画面で打ち込んだ名前。 */
export async function purgeRide(id: string, confirmRideId: string): Promise<PurgeResponse> {
  const body: PurgeRequest = { confirm_ride_id: confirmRideId };
  const result = await apiJson<PurgeResponse>(`rides/${checkRideId(id)}/purge`, { method: "POST", body: JSON.stringify(body) });
  invalidateRides();
  return result;
}

// ------------------------------------------------------------------ 処理の記録
export function loadRuns(id: string): Promise<RunsResponse> {
  return apiJson<RunsResponse>(`rides/${checkRideId(id)}/runs`);
}

export async function publishRun(id: string, runId: string): Promise<void> {
  await apiFetch(`rides/${checkRideId(id)}/published-run`, { method: "PUT", body: JSON.stringify({ run_id: runId }) });
  invalidateRides();
}

// ------------------------------------------------------------------ モデル
export function loadModels(): Promise<ModelsResponse> {
  return apiJson<ModelsResponse>("models");
}

export function loadModel(version: string): Promise<ModelRecord> {
  return apiJson<ModelRecord>(`models/${encodeURIComponent(version)}`);
}

export async function loadModelNotes(version: string): Promise<string> {
  return (await apiFetch(`models/${encodeURIComponent(version)}/notes`)).text();
}

export async function switchModel(version: string): Promise<void> {
  await apiFetch("models/current", { method: "PUT", body: JSON.stringify({ version }) });
}

// ------------------------------------------------------------------ 1 走行
export function loadRide(id: string): Promise<RideData> {
  return getJson<RideData>(`ride_${id}.json`);
}

export async function loadSpectrogram(id: string): Promise<{ meta: SpecMeta; url: string } | null> {
  try {
    const [meta, url] = await Promise.all([getJson<SpecMeta>(`spec_${id}.json`), getImageUrl(`spec_${id}.png`)]);
    return { meta, url };
  } catch {
    return null; // スペクトログラムがない走行（古いデータ）では表示しない
  }
}

// 生波形は約 1 分ごとのファイル（src/lib/wave.ts）。読んだ分は覚えておき、同じ分をもう一度選んでも読み直さない
const waveCache = new Map<string, Promise<Map<number, Waveform> | null>>();

/** chunk 番目の生波形のファイル（窓の添字 → 生波形）。ファイルが無ければ null（加速度の無い走行・古い形で処理した走行）。 */
export function loadWaveChunk(id: string, chunk: number): Promise<Map<number, Waveform> | null> {
  const name = waveFileName(checkRideId(id), chunk);
  let found = waveCache.get(name);
  if (!found) {
    found = getJson<WaveFile>(name).then(
      (f) => new Map(f.windows.map((w) => [w.i, w])),
      (e: unknown) => {
        if (e instanceof DataError && e.status === 404) return null;
        waveCache.delete(name); // 通信の失敗などは覚えず、次に選んだときに読み直す
        throw e;
      },
    );
    waveCache.set(name, found);
  }
  return found;
}

// ------------------------------------------------------------------ 読み込みの小道具
/** 非同期の読み込みを、画面の状態（値・失敗・読み直し）にする。 */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): { value: T | null; error: string | null; reload: () => void } {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const run = useCallback(load, deps);
  useEffect(() => {
    let alive = true;
    setError(null);
    run().then(
      (v) => alive && setValue(v),
      (e: Error) => alive && setError(e.message),
    );
    return () => {
      alive = false;
    };
  }, [run, version]);
  return { value, error, reload: () => setVersion((v) => v + 1) };
}
