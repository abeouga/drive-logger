// 走行ページ：地図・グラフ（タイムライン／スペクトログラム）・詳細パネルが、選択中の窓・カーソル・範囲を共有して連動する。
// PC は地図と詳細を横に並べ、下にグラフ。スマホ（1024px 未満）は 地図／グラフ／詳細 をタブで切り替える。
import { useEffect, useMemo, useState } from "react";
import { loadRide, loadSpectrogram, loadWaveforms, useRides, type RideData, type RideSummary, type SpecMeta, type Waveform } from "../lib/data";
import { fmtDate, fmtDuration, fmtKm, fmtTime } from "../lib/format";
import { listHref } from "../lib/route";
import { rankedHighlights, type Selection } from "../lib/series";
import { useTheme } from "../lib/theme";
import { useMediaQuery } from "../lib/media";
import MapView from "../components/MapView";
import Legend from "../components/Legend";
import Timeline from "../components/Timeline";
import Spectrogram from "../components/Spectrogram";
import DetailPanel from "../components/DetailPanel";
import Tabs from "../components/Tabs";
import LoadState from "../components/LoadState";

type ChartKey = "timeline" | "spectrogram";
type MobileKey = "map" | "chart" | "detail";

function NoGpsCard({ summary }: { summary: RideSummary }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-dashed border-line bg-surface p-6">
      <div className="text-sm font-semibold">この走行は GPS が捕捉できなかったため、地図は表示していません</div>
      <p className="text-xs leading-relaxed text-ink-2">
        記録の最初から最後まで衛星数が 0 でした（{fmtDuration(summary.duration_s)}）。直前の走行では測位できていたので、
        受信そのものの問題（GPS アンテナの接続など）と考えられますが、原因は確認中です。
      </p>
      <p className="text-xs leading-relaxed text-ink-2">
        速度が分からないため z_speed（速度で補正した逸脱）は計算できません。振動 rms と Isolation Forest のスコアを、記録開始からの時間で表示します。
      </p>
    </div>
  );
}

function SpecNote() {
  return (
    <p className="px-2 pb-1 text-[11px] leading-relaxed text-ink-2">
      濃いところほど、その周波数の振動が強いことを示します（この走行の中での相対値）。停車中に 20〜26 Hz 付近に出る横の帯は、
      アイドリング中のエンジンの振動と考えられます（1 回転に 1 回の振動とみなすと約 1,300〜1,500 rpm 相当。公称値とは未照合）。
      ロガーは置いただけの暫定の固定なので、置き方による揺れ（共振）も含みます。
    </p>
  );
}

export default function Ride({ id }: { id: string }) {
  const { rides, error: ridesError } = useRides();
  const summary = rides?.find((r) => r.id === id);
  const theme = useTheme();
  const wide = useMediaQuery("(min-width: 1024px)");
  const [data, setData] = useState<RideData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [spec, setSpec] = useState<{ meta: SpecMeta; url: string } | null>(null);
  const [waves, setWaves] = useState<Map<number, Waveform>>(new Map());
  const [hover, setHover] = useState<Selection>(null);
  const [selected, setSelected] = useState<Selection>(null);
  const [range, setRange] = useState<[number, number] | null>(null);
  const [chartTab, setChartTab] = useState<ChartKey>("timeline");
  const [mobileTab, setMobileTab] = useState<MobileKey>("map");

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    setSpec(null);
    setWaves(new Map());
    setHover(null);
    setSelected(null);
    setRange(null);
    loadRide(id).then(
      (d) => alive && setData(d),
      (e: Error) => alive && setError(e.message),
    );
    loadSpectrogram(id).then((s) => alive && setSpec(s));
    loadWaveforms(id).then((w) => alive && setWaves(w));
    return () => {
      alive = false;
    };
  }, [id]);

  const ranked = useMemo(() => (data ? rankedHighlights(data) : []), [data]);
  const hasMap = summary?.gps !== "none" && !!data?.columns.lat.some((v) => v !== null);
  const hasGps = !!data?.columns.has_gps.some(Boolean);

  if (!rides) return <LoadState error={ridesError} label="走行一覧" />;
  if (!summary) {
    return (
      <div className="flex flex-col gap-2">
        <p>{id} という走行はありません。</p>
        <a href={listHref} className="text-accent">← 走行一覧へ</a>
      </div>
    );
  }

  const header = (
    <>
      <a href={listHref} className="text-sm text-ink-2 hover:text-ink">← 走行一覧</a>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-sm text-ink-2">
            {summary.start_ms !== null ? `${fmtDate(summary.start_ms)} ${fmtTime(summary.start_ms)}` : "日時不明（GPS なし）"}
          </div>
          <h1 className="text-xl font-semibold">{summary.id}</h1>
          {summary.memo && <div className="mt-0.5 text-sm text-ink-2">{summary.memo}</div>}
        </div>
        <div className="tabular flex flex-wrap gap-x-5 gap-y-1 text-sm">
          <span><span className="text-ink-2">時間 </span>{fmtDuration(summary.duration_s)}</span>
          {summary.gps !== "none" && <span><span className="text-ink-2">距離 </span>{fmtKm(summary.distance_km)} km</span>}
          {summary.max_speed_kmh !== null && <span><span className="text-ink-2">最高 </span>{summary.max_speed_kmh.toFixed(0)} km/h</span>}
          <span><span className="text-ink-2">GPS 有効 </span>{Math.round(summary.fix_ratio * 100)}%</span>
        </div>
      </div>
    </>
  );

  if (!data) return (<div className="flex flex-col gap-4">{header}<LoadState error={error} label="走行データ" /></div>);

  const shared = { hover, selected, onHover: setHover, onSelect: setSelected };

  const mapBlock = (
    <div className="flex flex-col gap-2">
      {hasMap ? (
        <>
          <div className="h-[340px] overflow-hidden rounded-lg border border-line bg-surface sm:h-[420px]">
            <MapView data={data} theme={theme} range={range} ranked={ranked} {...shared} />
          </div>
          <Legend data={data} theme={theme} />
        </>
      ) : (
        <NoGpsCard summary={summary} />
      )}
    </div>
  );

  const detailBlock = (
    <div className="rounded-lg border border-line bg-surface p-4 lg:max-h-[460px] lg:overflow-y-auto">
      <DetailPanel data={data} selected={selected} ranked={ranked} waves={waves} theme={theme} onSelect={setSelected} />
    </div>
  );

  const chartBlock = (
    <div className="rounded-lg border border-line bg-surface p-2">
      <div className="flex flex-wrap items-center justify-between gap-2 px-2 pt-1">
        <Tabs
          label="グラフの種類"
          items={[{ key: "timeline", label: "タイムライン" }, ...(spec ? [{ key: "spectrogram" as const, label: "スペクトログラム" }] : [])]}
          value={chartTab}
          onChange={setChartTab}
        />
        <span className="text-[11px] text-ink-2">
          横軸：{data.has_abs_time ? "時刻（日本時間）" : "記録開始からの時間（GPS がないため時刻は不明）"}
        </span>
      </div>
      {chartTab === "timeline" || !spec ? (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-2 pt-2 text-[11px] text-ink-2">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-3 w-4 rounded-sm" style={{ background: "rgba(137,135,129,0.18)" }} />
              停止中{hasGps && "／GPS なし（濃い灰）"}
            </span>
            <span>ホイール・ピンチで拡大、下のバーで範囲を選ぶと地図がその区間に寄ります</span>
          </div>
          <div className={hasGps ? "h-[460px]" : "h-[340px]"}>
            <Timeline data={data} theme={theme} ranked={ranked} onRange={setRange} {...shared} />
          </div>
        </>
      ) : (
        <>
          <SpecNote />
          <Spectrogram data={data} spec={spec} theme={theme} onRange={setRange} {...shared} />
        </>
      )}
    </div>
  );

  if (!wide) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <div className="sticky top-0 z-10 -mx-4 bg-page/95 px-4 py-2 backdrop-blur">
          <Tabs
            label="表示の切り替え"
            className="w-full justify-between [&>button]:flex-1"
            items={[
              { key: "map", label: hasMap ? "地図" : "概要" },
              { key: "chart", label: "グラフ" },
              { key: "detail", label: selected !== null ? "詳細 ●" : "詳細" },
            ]}
            value={mobileTab}
            onChange={setMobileTab}
          />
        </div>
        {mobileTab === "map" && mapBlock}
        {mobileTab === "chart" && chartBlock}
        {mobileTab === "detail" && detailBlock}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {header}
      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-3">{mapBlock}</div>
        <div className="col-span-2">{detailBlock}</div>
      </div>
      {chartBlock}
    </div>
  );
}
