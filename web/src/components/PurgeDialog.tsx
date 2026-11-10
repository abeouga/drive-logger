// 完全に削除の確かめの画面（admin だけ。#82）。元に戻せないので、走行の名前を打ち込むまで消せない。
// API も同じ名前を受け取って確かめる（画面を通さずに呼んでも、名前が違えば断る）。
import { useEffect, useRef, useState } from "react";
import { TbAlertTriangle, TbLoader2 } from "react-icons/tb";
import { purgeRide } from "../lib/data";

export default function PurgeDialog({ rideId, onClose, onPurged }: { rideId: string; onClose: () => void; onPurged: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const matches = typed === rideId;

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  return (
    <dialog
      ref={dialog}
      aria-labelledby="purge-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
      }}
      onClose={onClose}
      className="card m-auto w-[min(32rem,calc(100vw-2rem))] p-0 text-ink backdrop:bg-black/40"
    >
      <form
        method="dialog"
        className="flex flex-col gap-4 p-5"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!matches || busy) return;
          setBusy(true);
          setError(null);
          try {
            await purgeRide(rideId, typed);
            dialog.current?.close();
            onPurged();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2 id="purge-title" className="flex items-center gap-2 text-base font-bold text-critical">
          <TbAlertTriangle aria-hidden className="size-5" />
          {rideId} を完全に削除します
        </h2>
        <div className="flex flex-col gap-2 text-sm">
          <p className="font-semibold">元に戻せません。ゴミ箱からも消えます。</p>
          <p>消すもの：生データ（その走行のすべてのファイル）・処理の結果・走行の台帳の 1 件・画面用のファイル。</p>
          <p className="text-ink-2">
            残るもの：処理の記録（run.json）と、学習したモデルの記録には、走行の ID だけが残ります。
            保存の仕組み（S3 のバージョニング）により、消したファイルの古い版は 30 日残り、その後に自動で消えます。
          </p>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          <span>
            確かめのため、走行の名前 <code className="font-mono font-semibold">{rideId}</code> を打ち込んでください
          </span>
          <input
            className="field font-mono"
            value={typed}
            onChange={(event) => setTyped(event.target.value.trim())}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            aria-invalid={typed !== "" && !matches}
            autoFocus
          />
        </label>
        {error && (
          <p role="alert" className="text-xs break-all text-critical">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-compact btn-secondary" disabled={busy} onClick={() => dialog.current?.close()}>
            やめる
          </button>
          <button type="submit" className="btn btn-compact btn-danger" disabled={!matches || busy} aria-busy={busy || undefined}>
            {busy ? <TbLoader2 aria-hidden className="size-4 animate-spin" /> : null}
            {busy ? "削除しています…" : "完全に削除する"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
