// 書き換えのボタン（admin だけに出す）。押す前に確かめ、終わるまで押せないようにし、失敗したら理由を出す。
// icon を渡すと、文字の代わりにアイコンだけを出す（label は読み上げの名前と、指を乗せたときの説明に使う）。
import { useState, type ReactNode } from "react";
import { TbLoader2 } from "react-icons/tb";

export default function ActionButton({
  label,
  icon,
  confirmText,
  onRun,
  tone = "plain",
  className = "",
}: {
  label: string;
  icon?: ReactNode;
  confirmText?: string;
  onRun: () => Promise<void>;
  tone?: "plain" | "primary" | "danger";
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const look = tone === "danger" ? "btn-danger" : tone === "primary" ? "btn-primary" : "btn-secondary";
  const iconOnly = icon !== undefined;
  return (
    <span className={`relative inline-flex flex-col gap-1 ${className}`}>
      <button
        type="button"
        disabled={busy}
        aria-label={iconOnly ? label : undefined}
        aria-busy={busy || undefined}
        title={iconOnly ? label : undefined}
        className={`btn btn-compact ${look} ${iconOnly ? "btn-icon" : ""}`}
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
        {iconOnly ? busy ? <TbLoader2 aria-hidden className="size-[18px] animate-spin" /> : icon : busy ? "処理中…" : label}
      </button>
      {error && (
        <span
          role="alert"
          className={
            iconOnly
              ? "absolute top-full right-0 z-10 mt-1 w-64 rounded-lg border border-line bg-surface p-2 text-xs break-all text-critical shadow-md"
              : "max-w-xs text-xs break-all text-critical"
          }
        >
          {error}
        </span>
      )}
    </span>
  );
}
