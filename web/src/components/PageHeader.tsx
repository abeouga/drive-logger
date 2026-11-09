// 画面の見出し（文之助の .page-header と同じ形：大きな太字・下に線）
import type { ReactNode } from "react";

/** 見出しの文字の形。見出しの横に別のもの（数値など）を並べる画面は、h1 にこれだけを使う */
export const pageTitleClass = "text-[clamp(28px,3vw,36px)] font-extrabold leading-[1.35] text-ink break-all";

/** 見出しの枠（下の線と余白） */
export const pageHeaderClass = "border-b border-line pt-[5px] pb-[15px]";

export default function PageHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <header className={pageHeaderClass}>
      <h1 className={pageTitleClass}>{title}</h1>
      {children && <div className="mt-1 max-w-3xl text-sm leading-[1.75] text-ink-2">{children}</div>}
    </header>
  );
}
