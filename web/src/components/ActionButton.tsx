// 書き換えのボタン（admin だけに出す）。押す前に確かめ、終わるまで押せないようにし、失敗したら理由を出す。
import { useState } from "react";

export default function ActionButton({
  label,
  confirmText,
  onRun,
  tone = "plain",
  className = "",
}: {
  label: string;
  confirmText?: string;
  onRun: () => Promise<void>;
  tone?: "plain" | "danger";
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const color = tone === "danger" ? "border-line text-ink-2 hover:border-critical hover:text-critical" : "border-line text-ink-2 hover:border-accent hover:text-ink";
  return (
    <span className={`inline-flex flex-col gap-1 ${className}`}>
      <button
        type="button"
        disabled={busy}
        className={`rounded border px-2 py-1 text-xs transition disabled:opacity-50 ${color}`}
        onClick={async (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (confirmText && !window.confirm(confirmText)) return;
          setBusy(true);
          setError(null);
          try {
            await onRun();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "処理中…" : label}
      </button>
      {error && <span className="max-w-xs text-[11px] break-all text-critical">{error}</span>}
    </span>
  );
}
