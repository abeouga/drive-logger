// 「この分析について」のモデルの記録：今使っているモデルの作り方（学習に使った走行・使わなかった理由・設定・ナレッジ）と、
// 版の一覧。admin は別の版に切り替えられる（全走行の点数付けし直しは AWS の Lambda が行い、数分かかる）。
import { useState } from "react";
import { loadModel, loadModelNotes, loadModels, switchModel, useLoad, type ModelRecord } from "../lib/data";
import { useAuth } from "../lib/auth/AuthGate";
import ActionButton from "./ActionButton";

const KIND = { idle: "停車", ride: "実走" } as const;
const REASON = { desk: "机上の試験", ride_nogps: "GPS が足りない", deleted: "画面で消した", failed: "処理に失敗した", unclassified: "分類できなかった" } as const;
const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

function Record({ record }: { record: ModelRecord }) {
  const notes = useLoad(() => loadModelNotes(record.version), [record.version]);
  const model = record.config.model as Record<string, unknown> | undefined;
  return (
    <div className="flex flex-col gap-3">
      <p>
        {fmt(record.created_at)} に {record.where === "lambda" ? "AWS の Lambda " : "ローカル"}で学習した版
        （コミット <code>{record.commit ?? "不明"}</code>）。学習に使った 1 秒は {record.train.n_windows.toLocaleString()} 個
        （記録の先頭・末尾 60 秒と、±16 g に達した 1 秒を除く）、速度補正ベースラインの区間は {record.summary.baseline_bins} 個です。
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="text-xs font-semibold text-ink">学習に使った走行</div>
          <ul className="mt-1 text-xs">
            {record.train.rides.map((r) => (
              <li key={r.ride_id} className="tabular">{r.ride_id}（{KIND[r.kind]}、{r.n_windows} 個）</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-xs font-semibold text-ink">使わなかった走行</div>
          <ul className="mt-1 text-xs">
            {record.excluded.map((r) => (
              <li key={r.ride_id} className="tabular">{r.ride_id}（{REASON[r.reason]}）</li>
            ))}
          </ul>
        </div>
      </div>
      {model && (
        <p className="text-xs">
          設定：速度の区間 {String(model.speed_bin_kmh)} km/h、候補とする z_speed &gt; {String(model.z_threshold)}、Isolation Forest は木 {String(model.n_estimators)} 本・外れの割合 {String(model.contamination)}。
          {record.forest && `Isolation Forest は速度も特徴量にして GPS のある 1 秒 ${record.forest.n_train.toLocaleString()} 個で学習し、しきい値は学習の 1 秒のスコアの上位 ${+((1 - record.forest.quantile) * 100).toFixed(3)}%（score_if > ${record.forest.threshold.toFixed(4)}）。`}
          ライブラリ：{Object.entries(record.libraries).map(([k, v]) => `${k} ${v}`).join("、")}
        </p>
      )}
      {notes.value && (
        <details className="rounded-lg border border-line bg-surface-muted px-3 py-2">
          <summary className="cursor-pointer text-xs">ナレッジ（notes.md）</summary>
          <pre className="mt-2 text-xs leading-relaxed whitespace-pre-wrap">{notes.value}</pre>
        </details>
      )}
    </div>
  );
}

export default function ModelInfo() {
  const { isAdmin } = useAuth();
  const models = useLoad(loadModels, []);
  const current = models.value?.current ?? null;
  const record = useLoad(async () => (current ? loadModel(current) : null), [current]);
  const [notice, setNotice] = useState<string | null>(null);
  if (models.error) return <p className="text-xs">モデルの記録を読めませんでした：{models.error}</p>;
  if (!models.value) return <p className="text-xs">モデルの記録を読み込み中…</p>;
  return (
    <div className="flex flex-col gap-4">
      {record.value ? <Record record={record.value} /> : <p>今使っている版：{current ?? "—"}</p>}
      <details>
        <summary className="cursor-pointer text-xs">モデルの版の一覧（{models.value.models.length}）</summary>
        <ul className="mt-2 flex flex-col gap-1">
          {models.value.models.map((m) => (
            <li key={m.version} className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-1 text-xs">
              <span className="tabular">
                {m.version}
                {m.version === current && <span className="pill pill-accent ml-2">使用中</span>}
                <span className="ml-2 text-ink-2">
                  {m.has_record ? `${fmt(m.created_at)}・${m.where === "lambda" ? "Lambda" : "ローカル"}・走行 ${m.n_rides}・1 秒 ${m.n_windows?.toLocaleString()}` : "記録なし（作り直しの前の版）"}
                </span>
              </span>
              {isAdmin && m.version !== current && m.has_record && (
                <ActionButton
                  label="このモデルに切り替える"
                  confirmText={`今使うモデルを ${m.version} にして、全走行を点数付けし直します（数分かかります）。よろしいですか？`}
                  onRun={async () => {
                    await switchModel(m.version);
                    setNotice(`${m.version} に切り替えを頼みました。全走行の点数付けし直しが終わると（数分）、画面に出ます`);
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      </details>
      {notice && <p className="text-xs">{notice}</p>}
    </div>
  );
}
