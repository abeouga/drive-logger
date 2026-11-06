// 走行ページ：地図とタイムラインと詳細パネルが、選択中の窓・カーソル・範囲を共有して連動する
import { useEffect, useMemo, useState } from "react";
import { findRide, loadRide, type RideData, type RideSummary } from "../lib/data";
import { fmtDate, fmtDuration, fmtKm, fmtTime } from "../lib/format";
import { listHref } from "../lib/route";
import { rankedHighlights, type Selection } from "../lib/series";
import { useTheme } from "../lib/theme";
import MapView from "../components/MapView";
import Legend from "../components/Legend";
import Timeline from "../components/Timeline";
import DetailPanel from "../components/DetailPanel";
import { Badge } from "../components/RideCard";

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

export default function Ride({ id }: { id: string }) {
  const summary = findRide(id);
  const theme = useTheme();
  const [data, setData] = useState<RideData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<Selection>(null);
  const [selected, setSelected] = useState<Selection>(null);
  const [range, setRange] = useState<[number, number] | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    setHover(null);
    setSelected(null);
    setRange(null);
    loadRide(id).then(setData, (e: Error) => setError(e.message));
  }, [id]);

  const ranked = useMemo(() => (data ? rankedHighlights(data) : []), [data]);
  const hasMap = summary?.gps !== "none" && !!data?.columns.lat.some((v) => v !== null);

  if (!summary) {
    return (
      <div className="flex flex-col gap-2">
        <p>{id} という走行はありません。</p>
        <a href={listHref} className="text-accent">← 走行一覧へ</a>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
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
          {summary.n_private > 0 && <Badge>自宅周辺 {summary.n_private} 窓は地図に出さない</Badge>}
        </div>
      </div>

      {error && <div className="rounded-lg border border-line bg-surface p-4 text-sm">読み込めませんでした：{error}</div>}
      {!data && !error && <div className="rounded-lg border border-line bg-surface p-4 text-sm text-ink-2">読み込み中…</div>}

      {data && (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div className="flex flex-col gap-2 lg:col-span-3">
              <div className={hasMap ? "h-[340px] overflow-hidden rounded-lg border border-line bg-surface sm:h-[420px]" : ""}>
                {hasMap ? (
                  <MapView data={data} theme={theme} hover={hover} selected={selected} range={range} ranked={ranked} onHover={setHover} onSelect={setSelected} />
                ) : (
                  <NoGpsCard summary={summary} />
                )}
              </div>
              {hasMap && <Legend data={data} theme={theme} />}
            </div>
            <div className="rounded-lg border border-line bg-surface p-4 lg:col-span-2 lg:max-h-[460px] lg:overflow-y-auto">
              <DetailPanel data={data} selected={selected} ranked={ranked} onSelect={setSelected} />
            </div>
          </div>

          <div className="rounded-lg border border-line bg-surface p-2">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-2 pt-1 text-[11px] text-ink-2">
              <span>横軸：{data.has_abs_time ? "時刻（日本時間）" : "記録開始からの時間（GPS がないため時刻は不明）"}</span>
              <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-4 rounded-sm" style={{ background: "rgba(137,135,129,0.18)" }} />停止中{data.columns.has_gps.some(Boolean) && "／GPS なし（濃い灰）"}</span>
              <span>ホイール・ピンチで拡大、下のバーで範囲を選ぶと地図がその区間に寄ります</span>
            </div>
            <div className={data.columns.has_gps.some(Boolean) ? "h-[460px]" : "h-[340px]"}>
              <Timeline data={data} theme={theme} hover={hover} selected={selected} ranked={ranked} onHover={setHover} onSelect={setSelected} onRange={setRange} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
