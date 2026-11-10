// 生波形のファイルの分け方（contracts/app/wave.schema.json）。
// pipeline は全部の 1 秒窓の生波形を、窓の添字 60 個（1 秒窓なので約 1 分）ごとのファイルに分けて書き出す。
// 画面は、選んだ窓を含むファイルだけを読む。

/** 1 ファイルに入る窓の数。pipeline の export.WAVE_CHUNK_WINDOWS と合わせる */
export const WAVE_CHUNK_WINDOWS = 60;

/** 窓の添字 i が入っているファイルの番号 */
export function waveChunkOf(i: number): number {
  return Math.floor(i / WAVE_CHUNK_WINDOWS);
}

/** 生波形のファイル名（番号は 3 桁の 0 詰め。例：wave_ride_20261109_030109_004.json） */
export function waveFileName(rideId: string, chunk: number): string {
  return `wave_${rideId}_${String(chunk).padStart(3, "0")}.json`;
}
