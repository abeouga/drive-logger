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
  tone?: "plain" | "primary" | "danger";
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const look = tone === "danger" ? "btn-danger" : tone === "primary" ? "btn-primary" : "btn-secondary";
  return (
    <span className={`inline-flex flex-col gap-1 ${className}`}>
      <button
        type="button"
        disabled={busy}
        className={`btn btn-compact ${look}`}
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
      {error && <span className="max-w-xs text-xs break-all text-critical">{error}</span>}
    </span>
  );
}
