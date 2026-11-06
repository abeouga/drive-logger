// 走行ページ。地図・タイムライン・詳細パネルはこの後の段階で追加する（docs/WEB_PLAN.md 6.）。
import { useEffect, useState } from "react";
import { findRide, loadRide, type RideData } from "../lib/data";
import { fmtDate, fmtDuration, fmtKm, fmtTime } from "../lib/format";
import { listHref } from "../lib/route";

export default function Ride({ id }: { id: string }) {
  const summary = findRide(id);
  const [data, setData] = useState<RideData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    loadRide(id).then(setData, (e: Error) => setError(e.message));
  }, [id]);

  if (!summary) {
    return (
      <div className="flex flex-col gap-2">
        <p>{id} という走行はありません。</p>
        <a href={listHref} className="text-accent">
          ← 走行一覧へ
        </a>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <a href={listHref} className="text-sm text-ink-2 hover:text-ink">
        ← 走行一覧
      </a>
      <div>
        <div className="text-sm text-ink-2">
          {summary.start_ms !== null ? `${fmtDate(summary.start_ms)} ${fmtTime(summary.start_ms)}` : "日時不明（GPS なし）"}
        </div>
        <h1 className="text-xl font-semibold">{summary.id}</h1>
        <div className="tabular mt-1 text-sm text-ink-2">
          {fmtDuration(summary.duration_s)}
          {summary.gps !== "none" && ` ・ ${fmtKm(summary.distance_km)} km`}
          {summary.memo && ` ・ ${summary.memo}`}
        </div>
      </div>
      <div className="rounded-lg border border-dashed border-line bg-surface p-6 text-sm text-ink-2">
        {error ? `読み込めませんでした：${error}` : data ? `1 秒窓 ${data.n} 個を読み込みました。地図とタイムラインは準備中です。` : "読み込み中…"}
      </div>
    </div>
  );
}
