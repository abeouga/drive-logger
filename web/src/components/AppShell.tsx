// 画面の外枠：左に白いメニュー（アプリ名・画面の切り替え・ログイン中のユーザー名）、右に中身。
// 形は文之助の外枠（.app-shell・.side-nav・.brand・.side-footer）にそろえる。980px 未満では、メニューを上の横並びの帯にする。
import type { ReactNode } from "react";
import type { IconType } from "react-icons";
import { TbInfoCircle, TbRoute, TbTrash } from "react-icons/tb";
import { aboutHref, listHref, trashHref, type Route } from "../lib/route";

// 名前を変えたら scripts/subset-brand-font.py で字体を作り直す（名前の字だけに絞った字体を使っている）
export const APP_NAME = "ドライブロガー";

// 印はゴミ箱のボタン（TrashButton）と同じ Tabler の絵にそろえる
type NavItem = { href: string; label: string; icon: IconType; active: boolean };

function NavLink({ item }: { item: NavItem }) {
  const Icon = item.icon;
  const base =
    "relative flex min-h-11 items-center gap-2.5 rounded-lg border px-[11px] py-[9px] text-[13px] font-bold transition-colors";
  const state = item.active
    ? "border-accent/40 bg-accent-wash text-accent-dark shadow-[inset_3px_0_0_var(--accent)]"
    : "border-transparent text-ink-2 hover:border-line hover:bg-accent-wash hover:text-accent-dark";
  const markState = item.active ? "border-accent bg-accent text-white" : "border-line-strong bg-surface-muted text-ink-2";
  return (
    <a href={item.href} aria-current={item.active ? "page" : undefined} className={`${base} ${state}`}>
      <span aria-hidden className={`grid size-[27px] shrink-0 place-items-center rounded-[7px] border ${markState}`}>
        <Icon className="size-[17px]" />
      </span>
      <span className="max-[980px]:sr-only">{item.label}</span>
    </a>
  );
}

export default function AppShell({
  route,
  isAdmin,
  userName,
  onSignOut,
  children,
}: {
  route: Route;
  isAdmin: boolean;
  userName: string | null;
  onSignOut: (() => void) | null;
  children: ReactNode;
}) {
  const items: NavItem[] = [
    // 走行の画面は一覧の下の画面なので、一覧を強調する
    { href: listHref, label: "走行一覧", icon: TbRoute, active: route.page === "list" || route.page === "ride" },
    { href: aboutHref, label: "この分析について", icon: TbInfoCircle, active: route.page === "about" },
    ...(isAdmin ? [{ href: trashHref, label: "ゴミ箱", icon: TbTrash, active: route.page === "trash" }] : []),
  ];

  return (
    <div className="grid min-h-screen grid-cols-[224px_minmax(0,1fr)] bg-page text-ink max-[980px]:grid-cols-1">
      <aside
        className={
          "sticky top-0 z-10 flex h-screen flex-col border-r border-line bg-surface shadow-[2px_0_10px_#1d35450d] " +
          "max-[980px]:h-auto max-[980px]:flex-row max-[980px]:items-center max-[980px]:border-r-0 max-[980px]:border-b max-[980px]:px-4 max-[980px]:py-2"
        }
      >
        <a
          href={listHref}
          className={
            "flex min-h-[76px] items-center justify-center border-b border-line px-[18px] py-[15px] hover:bg-surface-muted " +
            "max-[980px]:mr-auto max-[980px]:justify-start max-[980px]:pr-3 max-[980px]:min-h-0 max-[980px]:border-b-0 max-[980px]:pl-0 max-[980px]:py-0 max-[980px]:hover:bg-transparent"
          }
        >
          <strong className="font-brand text-[21px] font-normal tracking-[.06em] whitespace-nowrap text-ink max-[980px]:text-[15px] max-[980px]:tracking-normal">
            {APP_NAME}
          </strong>
        </a>
        <nav aria-label="メインメニュー" className="flex flex-col gap-1 px-2.5 py-3 max-[980px]:flex-row max-[980px]:p-0">
          {items.map((item) => (
            <NavLink key={item.href} item={item} />
          ))}
        </nav>
        {userName && (
          <div className="mt-auto flex items-center justify-between gap-2 border-t border-line bg-surface-muted px-[15px] py-3.5 max-[980px]:mt-0 max-[980px]:ml-2 max-[980px]:border-t-0 max-[980px]:bg-transparent max-[980px]:p-0">
            <strong className="min-w-0 truncate text-xs text-ink max-[980px]:hidden" title={userName}>
              {userName}
            </strong>
            {onSignOut && (
              <button
                type="button"
                onClick={onSignOut}
                className="btn btn-secondary btn-compact shrink-0"
              >
                ログアウト
              </button>
            )}
          </div>
        )}
      </aside>
      <main className="min-w-0 px-[clamp(22px,3vw,48px)] pt-[30px] pb-20 max-[980px]:px-4 max-[980px]:pb-16">{children}</main>
    </div>
  );
}
