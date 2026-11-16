// 加速度の記録の設定（rides.json の recording）を、画面に出す文にする。
import type { RecordingSettings } from "./types";

/** 実測の速さが、設定よりこの割合を超えて遅ければ「設定より遅い」とみなす（取りこぼし・I2C の詰まりの目安） */
export const SLOW_RATIO = 0.05;

const BUS_LABEL = { i2c: "I2C", spi: "SPI" } as const;

function hz(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** 一覧のカードの小さな印（例：「800 Hz」）。設定が無ければ実測を丸めて出す */
export function rateBadge(rec: RecordingSettings): string {
  return `${hz(rec.accel_odr_hz ?? Math.round(rec.accel_fs_hz))} Hz`;
}

/** firmware の版の短い名前（CT125_LOGGER_V3.7 → V3.7） */
export function firmwareLabel(firmware: string | null): string | null {
  if (firmware === null) return null;
  const m = /_(V\d+(?:\.\d+)*)$/.exec(firmware);
  return m ? m[1] : firmware;
}

/** センサーとつなぎ方（例：「ADXL345（I2C）」） */
export function sensorLabel(rec: RecordingSettings): string | null {
  const bus = rec.accel_bus ? BUS_LABEL[rec.accel_bus] : null;
  if (rec.accel_chip && bus) return `${rec.accel_chip}（${bus}）`;
  return rec.accel_chip ?? bus;
}

/** 実測が設定より遅すぎるか（設定が無ければ判断しない） */
export function isSlowerThanSet(rec: RecordingSettings): boolean {
  return rec.accel_odr_hz !== null && rec.accel_fs_hz < rec.accel_odr_hz * (1 - SLOW_RATIO);
}

/** 走行の画面の説明（(i) に出す）。特徴量を間引いて計算したときはそれも書く */
export function recordingNote(rec: RecordingSettings): string {
  const parts = [`実測 ${hz(rec.accel_fs_hz)} Hz`];
  if (rec.accel_odr_hz !== null) parts.unshift(`設定 ${hz(rec.accel_odr_hz)} Hz`);
  if (rec.feature_fs_hz < rec.accel_fs_hz * 0.9) parts.push(`振動の数値は ${hz(rec.feature_fs_hz)} Hz に間引いて計算`);
  if (isSlowerThanSet(rec)) parts.push("実測が設定より遅い（取りこぼしの疑い）");
  return parts.join("・");
}
