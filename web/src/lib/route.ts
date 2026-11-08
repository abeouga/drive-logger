// ハッシュルーティング（CloudFront の S3 の配信で、どのパスでも index.html を返さなくて済むように # を使う）
import { useEffect, useState } from "react";

export type Route = { page: "list" } | { page: "ride"; id: string } | { page: "about" } | { page: "trash" };

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#\/?/, "");
  const m = h.match(/^ride\/([\w-]+)/);
  if (m) return { page: "ride", id: m[1] };
  if (h.startsWith("about")) return { page: "about" };
  if (h.startsWith("trash")) return { page: "trash" };
  return { page: "list" };
}

export const rideHref = (id: string) => `#/ride/${id}`;
export const aboutHref = "#/about";
export const trashHref = "#/trash";
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
