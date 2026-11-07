// 地図の線の色：log_rms の 5 分位を、単色（青）の 5 段階で塗る（量は 1 つの色相の明暗で表す）。
// 明るい地図では「薄い＝静か、濃い＝大きい」、暗い地図では「暗い＝静か、明るい＝大きい」。
// 値はデータ可視化の参照パレットの青の段階（明：250〜650、暗：600〜200）。
import type { Theme } from "./theme";

export const QUINTILE: Record<Theme, string[]> = {
  light: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"],
  dark: ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"],
};

export const QUINTILE_LABELS = ["静か（下位 20%）", "20〜40%", "40〜60%", "60〜80%", "大きい（上位 20%）"];

/** 地図タイルのスタイル（OpenFreeMap、API キー不要） */
export const MAP_STYLE: Record<Theme, string> = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
