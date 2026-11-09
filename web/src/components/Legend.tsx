// 地図の凡例：5 段階の色と、その段階の rms の範囲（g）
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
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-2">
      <span className="text-muted">線の色＝その 1 秒の振動 rms（この走行の中での順位）</span>
      {QUINTILE.map((color, k) => (
        <span key={k} className="inline-flex items-center gap-1" title={QUINTILE_LABELS[k]}>
          <span className="inline-block h-1.5 w-5 rounded-full" style={{ background: color }} />
          <span className="tabular">{ranges[k] ? `${ranges[k]![0].toFixed(2)}–${ranges[k]![1].toFixed(2)} g` : "—"}</span>
        </span>
      ))}
      <span className="inline-flex items-center gap-1">
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-ink text-[9px] text-surface">1</span>
        見どころ（順位）
      </span>
    </div>
  );
}
