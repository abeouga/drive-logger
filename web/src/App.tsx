import { useRoute, listHref, aboutHref, trashHref } from "./lib/route";
import { useAuth } from "./lib/auth/AuthGate";
import { LOCAL_API } from "./lib/dataSource";
import RideList from "./pages/RideList";
import Ride from "./pages/Ride";
import About from "./pages/About";
import Trash from "./pages/Trash";

export default function App() {
  const route = useRoute();
  const { user, isAdmin, signOut } = useAuth();
  return (
    <div className="min-h-screen bg-page text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <a href={listHref} className="font-semibold tracking-tight">
            CT125 走行データ
          </a>
          <nav className="flex gap-4 text-sm text-ink-2">
            <a href={listHref} className={route.page === "list" ? "text-ink" : "hover:text-ink"}>
              走行一覧
            </a>
            <a href={aboutHref} className={route.page === "about" ? "text-ink" : "hover:text-ink"}>
              この分析について
            </a>
            {isAdmin && (
              <a href={trashHref} className={route.page === "trash" ? "text-ink" : "hover:text-ink"}>
                ゴミ箱
              </a>
            )}
            {user && !LOCAL_API && (
              <button type="button" onClick={() => void signOut()} className="hover:text-ink" title={`${user.username} でログイン中`}>
                ログアウト
              </button>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        {route.page === "list" && <RideList />}
        {route.page === "ride" && <Ride id={route.id} />}
        {route.page === "about" && <About />}
        {route.page === "trash" && <Trash />}
      </main>
    </div>
  );
}
