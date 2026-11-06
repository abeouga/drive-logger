// データの取り方はこのファイル 1 か所に集める。
//
// - 開発（npm run dev）：fetch("/data/<ファイル名>")。Vite の dev サーバー（server/s3-data.ts）が
//   S3 の app/v1/ から取る（または cache/ から返す）。AWS の認証情報はブラウザに出ない
// - ビルド（npm run build）：cache/ のファイルを HTML に埋め込み、fetch はしない（1 ファイルで動く）
import { useEffect, useState } from "react";
import type { RideData, RideSummary, RidesFile, SpecMeta, Waveform, WaveFile } from "./types";

export type * from "./types";

declare const __EMBED_DATA__: boolean; // vite.config.ts の define。build のときだけ true

// build のときだけ cache/ を読み込む（dev では空。import.meta.glob の引数は書き換えられないので固定）
const embeddedJson: Record<string, () => Promise<unknown>> = __EMBED_DATA__ ? import.meta.glob("../../cache/*.json", { import: "default" }) : {};
const embeddedImage: Record<string, () => Promise<string>> = __EMBED_DATA__
  ? import.meta.glob<string>("../../cache/*.png", { query: "?url", import: "default" })
  : {};

const SAFE_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;

export class DataError extends Error {}

async function getJson<T>(name: string): Promise<T> {
  if (!SAFE_NAME.test(name)) throw new DataError(`ファイル名が不正です：${name}`);
  const embedded = embeddedJson[`../../cache/${name}`];
  if (embedded) return (await embedded()) as T;
  const res = await fetch(`/data/${name}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 300);
    throw new DataError(`${name} を取得できませんでした（HTTP ${res.status}）${detail ? `：${detail}` : ""}`);
  }
  return (await res.json()) as T;
}

async function getImageUrl(name: string): Promise<string> {
  if (!SAFE_NAME.test(name)) throw new DataError(`ファイル名が不正です：${name}`);
  const embedded = embeddedImage[`../../cache/${name}`];
  if (embedded) return embedded();
  return `/data/${name}`; // dev サーバーが返す
}

// ------------------------------------------------------------------ 走行一覧
let ridesPromise: Promise<RideSummary[]> | null = null;

export function loadRides(): Promise<RideSummary[]> {
  ridesPromise ??= getJson<RidesFile>("rides.json")
    .then((f) => f.rides)
    .catch((e) => {
      ridesPromise = null; // 次に開いたときにやり直せるように
      throw e;
    });
  return ridesPromise;
}

export function useRides(): { rides: RideSummary[] | null; error: string | null } {
  const [rides, setRides] = useState<RideSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    loadRides().then(
      (r) => alive && setRides(r),
      (e: Error) => alive && setError(e.message),
    );
    return () => {
      alive = false;
    };
  }, []);
  return { rides, error };
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

export async function loadWaveforms(id: string): Promise<Map<number, Waveform>> {
  try {
    const f = await getJson<WaveFile>(`wave_${id}.json`);
    return new Map(f.windows.map((w) => [w.i, w]));
  } catch {
    return new Map();
  }
}
