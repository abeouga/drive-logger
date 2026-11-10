// 地図の凡例：5 段階の色と、その段階の rms の範囲（g）。基準を超えた振動があれば番号の丸も
import { useMemo } from "react";
import type { RideData } from "../lib/data";
import { QUINTILE, QUINTILE_LABELS } from "../lib/colors";

export default function Legend({ data }: { data: RideData }) {
  const ranges = useMemo(() => {
    const c = data.columns;
    return [0, 1, 2, 3, 4].map((k) => {
      const v = c.rms.filter((r, i) => r !== null && c.cls[i] === k) as number[];
      return v.length ? [Math.min(...v), Math.max(...v)] : null;
    });
  }, [data]);
  // 地図に番号の丸が無い走行（0 件・判定していない）では、丸の凡例を出さない
  const hasAnomaly = data.columns.anomaly.some(Boolean);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
      <span className="text-muted">線の色＝その 1 秒の振動 rms（この走行の中での順位）</span>
      {QUINTILE.map((color, k) => (
        <span key={k} className="inline-flex items-center gap-1" title={QUINTILE_LABELS[k]}>
          <span className="inline-block h-1.5 w-5 rounded-full" style={{ background: color }} />
          <span className="tabular">{ranges[k] ? `${ranges[k]![0].toFixed(2)}–${ranges[k]![1].toFixed(2)} g` : "—"}</span>
        </span>
      ))}
      {hasAnomaly && (
        <span className="inline-flex items-center gap-1">
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-ink text-xs text-surface">1</span>
          基準を超えた振動（スコアの高い順の番号）
        </span>
      )}
    </div>
  );
}
