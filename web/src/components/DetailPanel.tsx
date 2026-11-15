// 詳細パネル：何も選んでいないときは基準を超えた振動の一覧、選んだら その 1 秒の値
import type { ReactNode } from "react";
import type { RideData, Waveform } from "../lib/data";
import { fmtElapsed, fmtTimeSec } from "../lib/format";
import { SCORE_LABEL, anomalyBasisText, anomalyEmptyText, isJudged, type Selection } from "../lib/series";
import InfoTip from "./InfoTip";
import WaveChart from "./WaveChart";

/** 選んだ 1 秒の生波形：読めた波形／読み込み中／ファイルにその 1 秒が無い／読めなかった */
export type WaveState = Waveform | "loading" | "missing" | "error";

interface Props {
  data: RideData;
  selected: Selection;
  ranked: number[];
  wave: WaveState;
  onSelect: (i: Selection) => void;
}

function when(d: RideData, i: number): string {
  const ms = d.columns.t_abs_ms?.[i];
  return ms ? fmtTimeSec(ms) : `起動から ${fmtElapsed(d.columns.t_rel[i] ?? 0)}`;
}

const num = (v: number | null, digits: number) => (v === null ? "—" : v.toFixed(digits));

function Row({ label, value, unit }: { label: ReactNode; value: string; unit?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-1.5 last:border-0">
      <span className="inline-flex items-center gap-1 text-xs text-ink-2">{label}</span>
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
          <span className="w-16 shrink-0 text-xs text-ink-2">{label}</span>
          <div className="h-2 flex-1 rounded-full bg-grid">
            <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.max(0, Math.min(1, v ?? 0)) * 100}%` }} />
          </div>
          <span className="tabular w-10 text-right text-xs">{v === null ? "—" : `${Math.round(v * 100)}%`}</span>
        </div>
      ))}
    </div>
  );
}

function WaveBlock({ wave }: { wave: WaveState }) {
  if (typeof wave === "object") return <WaveChart wave={wave} />;
  const text = {
    loading: "生波形を読み込んでいます…",
    // 全部の 1 秒を書き出しているので、無いのは加速度の記録が無い走行か、前の形（基準を超えた所だけ）で処理した走行
    missing: "この 1 秒の生波形はありません。加速度の記録が無い走行か、前の形で処理した走行です（処理し直すと表示されます）。",
    error: "生波形を読み込めませんでした。別の 1 秒を選ぶと読み直します。",
  }[wave];
  return <p className="mt-1 text-xs text-muted">{text}</p>;
}

export default function DetailPanel({ data, selected, ranked, wave, onSelect }: Props) {
  const c = data.columns;
  if (selected === null) {
    return (
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">基準を超えた振動</h2>
        {!isJudged(data) ? (
          <p className="text-xs leading-relaxed text-ink-2">{anomalyBasisText(data)}。</p>
        ) : (
          <>
            <p className="text-xs leading-relaxed text-ink-2">
              {anomalyBasisText(data)}{ranked.length > 0 && `（${ranked.length} か所。番号はスコアの高い順）`}。路面または車両に起因する振動の変化を示します。
              {data.anomaly.model_version && <span className="text-muted">（モデルの版 {data.anomaly.model_version}）</span>}
            </p>
            {ranked.length === 0 && <p className="text-xs text-muted">{anomalyEmptyText(data)}。</p>}
          </>
        )}
        <p className="text-xs leading-relaxed text-ink-2">地図の線やグラフをクリックすると、その 1 秒の値をここに表示します。</p>
        {ranked.length > 0 && (
          <ol className="flex flex-col">
            {ranked.map((i, k) => (
              <li key={i}>
                <button
                  onClick={() => onSelect(i)}
                  className="flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left hover:bg-accent-wash"
                >
                  <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-ink text-xs text-surface">{k + 1}</span>
                  <span className="tabular w-20 shrink-0 text-xs">{when(data, i)}</span>
                  <span className="tabular flex-1 text-xs text-ink-2">
                    {c.speed[i] !== null && `${num(c.speed[i], 0)} km/h ・ `}rms {num(c.rms[i], 2)} g
                  </span>
                  <span className="tabular text-xs">
                    {SCORE_LABEL[data.anomaly.method]} {num(c.anomaly_score[i], 2)}
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
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="tabular text-lg font-semibold">{when(data, i)}</span>
          {rank >= 0 && <span className="text-xs text-ink-2">基準を超えた振動 {rank + 1} 番目</span>}
        </div>
        <button onClick={() => onSelect(null)} className="btn btn-secondary btn-compact shrink-0">
          一覧へ
        </button>
      </div>
      {/* (i) の吹き出しを、この表の幅で出す */}
      <div className="relative">
        <Row label="速度" value={c.has_gps[i] ? num(c.speed[i], 1) : "GPS なし"} unit={c.has_gps[i] ? "km/h" : undefined} />
        <Row label="振動 rms" value={num(c.rms[i], 3)} unit="g" />
        <Row label="振れ幅（最大−最小）" value={num(c.p2p[i], 2)} unit="g" />
        <Row label="z_speed（速度で補正した逸脱）" value={num(c.z[i], 2)} />
        <Row
          label={
            <>
              score_if（Isolation Forest）
              <InfoTip label="注意書きを開く">
                値の大きい所は、路面または車両に起因する振動の変化を示します。ロガーの取り付け方による揺れが含まれることもあります。
              </InfoTip>
            </>
          }
          value={num(c.score_if[i], 3)}
        />
      </div>
      <Bands data={data} i={i} />
      <div>
        <div className="text-xs text-ink-2">この 1 秒の生波形（各軸の平均＝重力を引いたもの）</div>
        <WaveBlock wave={wave} />
      </div>
      <div className="flex flex-wrap gap-1">
        {c.is_stopped[i] && <span className="pill pill-muted">停止中（5 km/h 未満）</span>}
        {c.is_edge[i] && <span className="pill pill-muted">記録の先頭・末尾 60 秒</span>}
        {c.is_clipped[i] && <span className="pill pill-muted">±16 g に達したサンプルを含む</span>}
      </div>
    </div>
  );
}
