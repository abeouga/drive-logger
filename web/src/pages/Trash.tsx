// ゴミ箱（admin だけ）：画面から消した走行の一覧と「戻す」。机上と判定した走行（画面に出さない）も見られる。
import { invalidateRides, loadFullLedger, restoreRide, useLoad, type LedgerRide } from "../lib/data";
import { useAuth } from "../lib/auth/AuthGate";
import { fmtDuration } from "../lib/format";
import { listHref } from "../lib/route";
import ActionButton from "../components/ActionButton";
import LoadState from "../components/LoadState";

const KIND_LABEL: Record<string, string> = { desk: "机上", idle: "停車", ride: "実走", ride_nogps: "実走（GPS なし）" };

function Row({ ride, onRestored }: { ride: LedgerRide; onRestored: () => void }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3">
      <div className="flex flex-col">
        <span className="font-semibold">{ride.id}</span>
        <span className="text-xs text-ink-2">
          {KIND_LABEL[ride.kind ?? ""] ?? "未分類"}
          {ride.summary && `・${fmtDuration(ride.summary.duration_s)}`}
          {ride.original_name && `・元の名前 ${ride.original_name}`}
          {ride.deleted_at && `・${new Date(ride.deleted_at).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })} に消した`}
        </span>
        {ride.summary?.memo && <span className="mt-0.5 line-clamp-1 text-xs text-ink-2">{ride.summary.memo}</span>}
      </div>
      {ride.deleted && (
        <ActionButton
          label="戻す"
          onRun={async () => {
            await restoreRide(ride.id);
            onRestored();
          }}
        />
      )}
    </li>
  );
}

export default function Trash() {
  const { isAdmin } = useAuth();
  const { value: rides, error, reload } = useLoad(loadFullLedger, []);
  if (!isAdmin) return <p className="text-sm text-ink-2">このページは admin だけが使えます。<a href={listHref} className="text-accent">走行一覧へ</a></p>;
  if (!rides) return <LoadState error={error} label="走行の台帳" />;
  const deleted = rides.filter((r) => r.deleted);
  const hidden = rides.filter((r) => !r.deleted && r.kind === "desk");
  const refresh = () => {
    invalidateRides();
    reload();
  };
  return (
    <div className="flex flex-col gap-6">
      <section>
        <h1 className="text-xl font-semibold">ゴミ箱</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">
          画面から消した走行です。消しても生データと処理の結果は残ります。消した走行は画面に出さず、学習にも使いません。
          「戻す」と一覧に戻ります（画面用のデータは数秒で戻ります）。
        </p>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">消した走行（{deleted.length}）</h2>
        {deleted.length === 0 ? <p className="text-sm text-ink-2">ありません。</p> : (
          <ul className="flex flex-col gap-2">{deleted.map((r) => <Row key={r.id} ride={r} onRestored={refresh} />)}</ul>
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">机上と判定した走行（画面に出さない・学習に使わない）（{hidden.length}）</h2>
        <p className="text-xs text-ink-2">振動の中央値が 0.05 g 未満（エンジンの振動が無い）の走行です。分類は処理のたびに自動で付きます。</p>
        <ul className="flex flex-col gap-2">
          {hidden.map((r) => (
            <li key={r.id} className="flex items-center justify-between rounded-lg border border-dashed border-line px-4 py-2 text-sm">
              <span>{r.id}</span>
              <span className="text-xs text-ink-2">{r.summary ? `振動 rms 中央値 ${r.summary.rms_median.toFixed(3)} g` : ""}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
