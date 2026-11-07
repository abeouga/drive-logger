import { useRoute, listHref, aboutHref } from "./lib/route";
import { useAuth } from "./lib/auth/AuthGate";
import RideList from "./pages/RideList";
import Ride from "./pages/Ride";
import About from "./pages/About";

export default function App() {
  const route = useRoute();
  const { user, signOut } = useAuth();
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
            {user && (
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
      </main>
      <footer className="mx-auto max-w-6xl px-4 pb-8 text-xs leading-relaxed text-muted">
        健康な車両の走行データから作った「速度で補正した正常時のベースライン」からの逸脱を表示しています。故障データは含まれていません。
        値の大きい区間は、路面または車両に起因する振動の変化を示すもので、車両の異常と断定するものではありません。
      </footer>
    </div>
  );
}
