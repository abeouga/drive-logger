// 走行ページの「処理の記録」：今どの処理の結果を出しているか（日時・Lambda かローカルか・コミット・モデルの版）と、
// この走行を処理した記録の一覧。admin は前の結果に戻せる。
import { useState } from "react";
import { loadRuns, publishRun, useLoad, type RunInfo } from "../lib/data";
import { useAuth } from "../lib/auth/AuthGate";
import ActionButton from "./ActionButton";

const WHERE = { lambda: "AWS の Lambda ", local: "ローカル" } as const;
const ACTION = { process: "処理", retrain: "学習し直し" } as const;

const fmt = (iso: string) => new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });

function describe(run: RunInfo): string {
  return `${fmt(run.created_at)}・${WHERE[run.where]}の${ACTION[run.action]}・モデル ${run.model_version ?? "—"}・コミット ${run.commit ?? "不明"}`;
}

export default function RunHistory({ rideId }: { rideId: string }) {
  const { isAdmin } = useAuth();
  const { value, error, reload } = useLoad(() => loadRuns(rideId), [rideId]);
  const [notice, setNotice] = useState<string | null>(null);
  if (error) return <p className="text-xs text-ink-2">処理の記録を読めませんでした：{error}</p>;
  if (!value) return null;
  const published = value.runs.find((r) => r.published);
  return (
    <details className="card px-4 py-3 text-sm">
      <summary className="cursor-pointer text-ink-2">
        処理の記録：{published ? describe(published) : "公開中の結果はありません"}
        {value.runs.length > 1 && `（ほか ${value.runs.length - 1} 回）`}
      </summary>
      <ul className="mt-3 flex flex-col gap-2">
        {value.runs.map((run) => (
          <li key={run.run_id} className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2">
            <div className="flex flex-col">
              <span className="text-xs">
                {describe(run)}
                {run.published && <span className="pill pill-accent ml-2">公開中</span>}
                {run.status === "failed" && <span className="pill pill-critical ml-2">失敗</span>}
              </span>
              <span className="text-xs text-muted">{run.run_id}</span>
              {run.error && <span className="text-xs break-all text-ink-2">{run.error}</span>}
            </div>
            {isAdmin && !run.published && run.status === "succeeded" && (
              <ActionButton
                label="この結果に戻す"
                confirmText={`${rideId} の画面に出す結果を、${fmt(run.created_at)} の処理の結果にします。よろしいですか？`}
                onRun={async () => {
                  await publishRun(rideId, run.run_id);
                  setNotice("切り替えました。画面用のデータは数秒で入れ替わります（再読み込みで表示されます）");
                  reload();
                }}
              />
            )}
          </li>
        ))}
      </ul>
      {notice && <p className="mt-2 text-xs text-ink-2">{notice}</p>}
    </details>
  );
}
