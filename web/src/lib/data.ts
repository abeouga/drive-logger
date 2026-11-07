// 画面が使うデータの読み込み（走行一覧・1 走行・スペクトログラム・生波形）。
// 「どこから取るか」は src/lib/dataSource.ts が受け持ち、ここは「何を読むか」だけを書く。
// 1 ファイル版（embedded）だけは、HTML に埋め込んだ cache/ のデータをここで直接読む。
import { useEffect, useState } from "react";
import { DATA_MODE, DataError, fetchDataFile } from "./dataSource";
import type { RideData, RideSummary, RidesFile, SpecMeta, Waveform, WaveFile } from "./types";

export type * from "./types";
export { DataError };

declare const __EMBED_DATA__: boolean; // vite.config.ts の define。embedded のときだけ true

// embedded のときだけ cache/ を読み込む（それ以外では空。import.meta.glob の引数は書き換えられないので固定）
const embeddedJson: Record<string, () => Promise<unknown>> = __EMBED_DATA__ ? import.meta.glob("../../cache/*.json", { import: "default" }) : {};
const embeddedImage: Record<string, () => Promise<string>> = __EMBED_DATA__
  ? import.meta.glob<string>("../../cache/*.png", { query: "?url", import: "default" })
  : {};

const SAFE_NAME = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/;

function checkName(name: string): void {
  if (!SAFE_NAME.test(name)) throw new DataError(`ファイル名が不正です：${name}`);
}

async function getJson<T>(name: string): Promise<T> {
  checkName(name);
  const embedded = embeddedJson[`../../cache/${name}`];
  if (embedded) return (await embedded()) as T;
  const response = await fetchDataFile(name);
  return (await response.json()) as T;
}

// 画像の URL。hosted ではログインが要るので <img src> に直接書けず、取ってきた中身から URL を作る
const imageUrlCache = new Map<string, Promise<string>>();

async function getImageUrl(name: string): Promise<string> {
  checkName(name);
  const embedded = embeddedImage[`../../cache/${name}`];
  if (embedded) return embedded();
  if (DATA_MODE === "dev") return `/data/${name}`; // dev サーバーがそのまま返す
  let url = imageUrlCache.get(name);
  if (!url) {
    url = fetchDataFile(name).then(async (response) => URL.createObjectURL(await response.blob()));
    imageUrlCache.set(name, url);
  }
  return url;
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
