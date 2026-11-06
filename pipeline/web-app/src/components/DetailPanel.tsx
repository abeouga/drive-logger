// 詳細パネル：何も選んでいないときは見どころの一覧、選んだら その 1 秒の値
import type { RideData } from "../lib/data";
import { fmtElapsed, fmtTimeSec } from "../lib/format";
import { BASIS_TEXT, type Selection } from "../lib/series";

interface Props {
  data: RideData;
  selected: Selection;
  ranked: number[];
  onSelect: (i: Selection) => void;
}

function when(d: RideData, i: number): string {
  const ms = d.columns.t_abs_ms?.[i];
  return ms ? fmtTimeSec(ms) : `起動から ${fmtElapsed(d.columns.t_rel[i] ?? 0)}`;
}

const num = (v: number | null, digits: number) => (v === null ? "—" : v.toFixed(digits));

function Row({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-1.5 last:border-0">
      <span className="text-xs text-ink-2">{label}</span>
      <span className="tabular text-sm">
        {value}
        {unit && <span className="ml-1 text-xs text-ink-2">{unit}</span>}
      </span>
    </div>
  );
}

function Bands({ data, i }: { data: RideData; i: number }) {
  const c = data.columns;
  const items: [string, number | null][] = [
    ["1〜5 Hz", c.band_1_5[i]],
    ["5〜15 Hz", c.band_5_15[i]],
    ["15〜40 Hz", c.band_15_40[i]],
  ];
  return (
    <div className="flex flex-col gap-1.5">
      <div className="text-xs text-ink-2">帯域ごとの振動の割合（1〜40 Hz の合計に対する比）</div>
      {items.map(([label, v]) => (
        <div key={label} className="flex items-center gap-2">
          <span className="w-16 shrink-0 text-[11px] text-ink-2">{label}</span>
          <div className="h-2 flex-1 rounded-full bg-grid">
            <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.max(0, Math.min(1, v ?? 0)) * 100}%` }} />
          </div>
          <span className="tabular w-10 text-right text-[11px]">{v === null ? "—" : `${Math.round(v * 100)}%`}</span>
        </div>
      ))}
    </div>
  );
}

export default function DetailPanel({ data, selected, ranked, onSelect }: Props) {
  const c = data.columns;
  if (selected === null) {
    return (
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">見どころ</h2>
        <p className="text-xs leading-relaxed text-ink-2">{BASIS_TEXT[data.highlight_basis]}。地図の線やグラフをクリックすると、その 1 秒の値をここに表示します。</p>
        {ranked.length === 0 ? (
          <p className="text-xs text-muted">この走行には対象の窓がありません（記録が短く、先頭・末尾 60 秒を除くと残らないため）。</p>
        ) : (
          <ol className="flex flex-col">
            {ranked.map((i, k) => (
              <li key={i}>
                <button
                  onClick={() => onSelect(i)}
                  className="flex w-full items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-accent-wash"
                >
                  <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink text-[10px] text-surface">{k + 1}</span>
                  <span className="tabular w-20 shrink-0 text-xs">{when(data, i)}</span>
                  <span className="tabular flex-1 text-xs text-ink-2">
                    {c.speed[i] !== null && `${num(c.speed[i], 0)} km/h ・ `}rms {num(c.rms[i], 2)} g
                  </span>
                  <span className="tabular text-xs">
                    {data.highlight_basis === "score_if_top" ? `IF ${num(c.score_if[i], 2)}` : `z ${num(c.z[i], 2)}`}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    );
  }

  const i = selected;
  const rank = ranked.indexOf(i);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs text-ink-2">選んだ 1 秒{rank >= 0 && `（見どころ ${rank + 1} 位）`}</div>
          <div className="tabular text-lg font-semibold">{when(data, i)}</div>
        </div>
        <button onClick={() => onSelect(null)} className="rounded border border-line px-2 py-1 text-xs text-ink-2 hover:text-ink">
          見どころ一覧へ
        </button>
      </div>
      <div>
        <Row label="速度" value={c.has_gps[i] ? num(c.speed[i], 1) : "GPS なし"} unit={c.has_gps[i] ? "km/h" : undefined} />
        <Row label="振動 rms" value={num(c.rms[i], 3)} unit="g" />
        <Row label="振れ幅（最大−最小）" value={num(c.p2p[i], 2)} unit="g" />
        <Row label="z_speed（速度で補正した逸脱）" value={num(c.z[i], 2)} />
        <Row label="score_if（Isolation Forest）" value={num(c.score_if[i], 3)} />
      </div>
      <Bands data={data} i={i} />
      <div className="flex flex-wrap gap-1 text-[11px] text-ink-2">
        {c.is_stopped[i] && <span className="rounded border border-line px-1.5 py-0.5">停止中（5 km/h 未満）</span>}
        {c.is_edge[i] && <span className="rounded border border-line px-1.5 py-0.5">記録の先頭・末尾 60 秒</span>}
        {c.is_private[i] && <span className="rounded border border-line px-1.5 py-0.5">自宅周辺のため地図に出さない</span>}
        {c.is_clipped[i] && <span className="rounded border border-line px-1.5 py-0.5">±16 g に達したサンプルを含む</span>}
      </div>
      <p className="text-[11px] leading-relaxed text-muted">
        値の大きい窓は、路面または車両に起因する振動の変化を示します。ロガーは車体に置いただけの暫定の固定なので、置き方による揺れも含みます。
      </p>
    </div>
  );
}
