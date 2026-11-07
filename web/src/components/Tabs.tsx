// タブ（キーボードの左右でも切り替えられる）
import { useRef } from "react";

export interface TabItem<K extends string> {
  key: K;
  label: string;
}

export default function Tabs<K extends string>({ items, value, onChange, label, className = "" }: { items: TabItem<K>[]; value: K; onChange: (k: K) => void; label: string; className?: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, k: number) => {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    const next = (k + d + items.length) % items.length;
    onChange(items[next].key);
    refs.current[next]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className={`inline-flex rounded-lg border border-line bg-surface p-0.5 ${className}`}>
      {items.map((t, k) => (
        <button
          key={t.key}
          ref={(el) => {
            refs.current[k] = el;
          }}
          role="tab"
          aria-selected={value === t.key}
          tabIndex={value === t.key ? 0 : -1}
          onClick={() => onChange(t.key)}
          onKeyDown={(e) => onKey(e, k)}
          className={`rounded-md px-3 py-1 text-sm transition ${value === t.key ? "bg-accent-wash font-semibold text-ink ring-1 ring-accent/40" : "text-ink-2 hover:text-ink"}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
