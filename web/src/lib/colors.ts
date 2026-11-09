// 地図の線の色：log_rms の 5 分位を、単色（青）の 5 段階で塗る（量は 1 つの色相の明暗で表す）。
// 「薄い＝静か、濃い＝大きい」。真ん中の段を主の色（--accent と同じ #23699e）にし、
// 明るい地図（positron）の上でいちばん薄い段も見え、隣どうしの明るさの差がそろう値にしてある。
export const QUINTILE = ["#74abd6", "#4a8cc2", "#23699e", "#174f7a", "#0b3456"];

export const QUINTILE_LABELS = ["静か（下位 20%）", "20〜40%", "40〜60%", "60〜80%", "大きい（上位 20%）"];

/** 系列の色：主の色の青を先頭に、橙・緑（3 色まではどの組も色覚の違いで見分けられる） */
export const SERIES = ["#23699e", "#eb6834", "#1baf7a"];

/** 地図タイルのスタイル（OpenFreeMap、API キー不要） */
export const MAP_STYLE = "https://tiles.openfreemap.org/styles/positron";
