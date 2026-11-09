// グラフと地図は CSS 変数を直接使えないので、描くときに index.css の役割の色を読む。

/** CSS 変数（index.css の役割の色）を読む */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
