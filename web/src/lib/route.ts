// ハッシュルーティング（1 ファイル配信・署名付き URL でも動くように、パスではなく # を使う）
import { useEffect, useState } from "react";

export type Route = { page: "list" } | { page: "ride"; id: string } | { page: "about" };

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#\/?/, "");
  const m = h.match(/^ride\/([\w-]+)/);
  if (m) return { page: "ride", id: m[1] };
  if (h.startsWith("about")) return { page: "about" };
  return { page: "list" };
}

export const rideHref = (id: string) => `#/ride/${id}`;
export const aboutHref = "#/about";
export const listHref = "#/";

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
