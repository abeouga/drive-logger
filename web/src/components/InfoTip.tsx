// (i) のマークにしまう短い注意書き。押すと開け閉めし（スマホ）、マウスを重ねても開く（PC）。外を押すか Esc で閉じる。
// 吹き出しは、いちばん近い position: relative の親の幅に合わせて、その親の下に出す（細い欄でもはみ出さないため）。
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { TbInfoCircle } from "react-icons/tb";

export default function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const [pinned, setPinned] = useState(false); // 押して開いた
  const [hovered, setHovered] = useState(false); // マウスを重ねて開いた
  const open = pinned || hovered;
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const close = () => {
      setPinned(false);
      setHovered(false);
    };
    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span
      ref={ref}
      className="inline-flex align-middle"
      onPointerEnter={(e) => e.pointerType === "mouse" && setHovered(true)}
      onPointerLeave={(e) => e.pointerType === "mouse" && setHovered(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={id}
        // マウスを重ねて開いているときに押すと、離しても開いたままにする。開いたままのときに押すと閉じる
        onClick={() => {
          if (pinned) {
            setPinned(false);
            setHovered(false);
          } else setPinned(true);
        }}
        className={
          "inline-flex h-5 w-5 items-center justify-center rounded-full text-ink-2 hover:text-accent-dark " +
          "focus-visible:outline-2 focus-visible:outline-accent " +
          (open ? "text-accent-dark" : "")
        }
      >
        <TbInfoCircle aria-hidden className="h-4 w-4" />
      </button>
      <span
        id={id}
        role="note"
        hidden={!open}
        className="absolute inset-x-0 top-full z-20 mt-1 rounded-lg border border-line bg-surface p-2.5 text-xs leading-relaxed text-ink-2 shadow-md"
      >
        {children}
      </span>
    </span>
  );
}
