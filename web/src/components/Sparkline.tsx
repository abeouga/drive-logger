// 走行カードの小さな折れ線（1 秒 rms を 60 区間の平均にしたもの）。
// 1 系列なので凡例は付けず、カードの見出しで名前を示す。カーソルで値を出す。
import { useState } from "react";
import { fmtElapsed } from "../lib/format";

interface Props {
  values: (number | null)[];
  durationS: number;
  height?: number;
}

const W = 240;

export default function Sparkline({ values, durationS, height = 44 }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const finite = values.filter((v): v is number => v !== null);
  if (finite.length < 2) return <div style={{ height }} />;
  const max = Math.max(...finite);
  const pad = 3;
  const x = (i: number) => (i / (values.length - 1)) * W;
  const y = (v: number) => height - pad - (v / max) * (height - pad * 2);

  // null をまたぐ所で線を切る
  let d = "";
  values.forEach((v, i) => {
    if (v === null) return;
    d += `${i > 0 && values[i - 1] !== null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left) / r.width) * (values.length - 1));
    setHover(Math.max(0, Math.min(values.length - 1, i)));
  };
  const hv = hover !== null ? values[hover] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${height}`}
        preserveAspectRatio="none"
        className="block w-full"
        style={{ height }}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label={`振動 rms の推移。最大 ${max.toFixed(2)} g`}
      >
        <line x1={0} x2={W} y1={height - pad} y2={height - pad} stroke="var(--axis)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        {hover !== null && hv !== null && (
          <line x1={x(hover)} x2={x(hover)} y1={0} y2={height} stroke="var(--muted)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      {hover !== null && hv !== null && (
        <div
          className="tabular pointer-events-none absolute -top-7 rounded border border-line bg-surface px-1.5 py-0.5 text-xs whitespace-nowrap text-ink shadow-sm"
          style={{ left: `${(hover / (values.length - 1)) * 100}%`, transform: "translateX(-50%)" }}
        >
          {fmtElapsed((hover / (values.length - 1)) * durationS)} 付近　{hv.toFixed(2)} g
        </div>
      )}
    </div>
  );
}
