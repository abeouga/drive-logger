import { useRoute } from "./lib/route";
import { useAuth } from "./lib/auth/AuthGate";
import { LOCAL_API } from "./lib/dataSource";
import AppShell from "./components/AppShell";
import RideList from "./pages/RideList";
import Ride from "./pages/Ride";
import About from "./pages/About";
import Trash from "./pages/Trash";

export default function App() {
  const route = useRoute();
  const { user, isAdmin, signOut } = useAuth();
  return (
    <AppShell
      route={route}
      isAdmin={isAdmin}
      userName={user?.username ?? null}
      // 手元のデータ API（npm run dev:local）はログインしないので、ログアウトを出さない
      onSignOut={user && !LOCAL_API ? () => void signOut() : null}
    >
      {route.page === "list" && <RideList />}
      {route.page === "ride" && <Ride id={route.id} />}
      {route.page === "about" && <About />}
      {route.page === "trash" && <Trash />}
    </AppShell>
  );
}
