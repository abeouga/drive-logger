// データ API の呼び出し口。どの画面も、ここを通してだけ API を呼ぶ（ログインのトークンを付ける）。
//   公開版：CloudFront の /api/* → データ API
//   dev    ：Vite の dev サーバーが /api/* を公開ドメインへ中継する（vite.config.ts）。ログインは公開版と同じ
import { accessToken, signIn } from "./auth/authClient";

declare const __LOCAL_API__: boolean; // vite.config.ts の define。npm run dev:local のときだけ true（ログインしない）

export const LOCAL_API = __LOCAL_API__;

export class DataError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
  }
}

/** /api/<path> を呼ぶ。失敗したら DataError（ステータス付き）。 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!LOCAL_API) {
    const token = await accessToken();
    if (!token) return redirectToLogin();
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/${path}`, { ...init, headers, cache: "no-store" });
  if (response.status === 401 && !LOCAL_API) return redirectToLogin();
  if (!response.ok) throw await errorFrom(path, response);
  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await (await apiFetch(path, init)).json()) as T;
}

/** 画面用のデータファイル（rides.json・ride_<id>.json・spec_<id>.png など）。 */
export function fetchDataFile(name: string): Promise<Response> {
  return apiFetch(`data/${name}`);
}

/** ログインが切れていたら、ログイン画面へ移る（この後の処理は続かない）。 */
async function redirectToLogin(): Promise<never> {
  await signIn();
  throw new DataError("ログインし直しています", 401);
}

async function errorFrom(path: string, response: Response): Promise<DataError> {
  const text = (await response.text()).slice(0, 300);
  let detail = text;
  try {
    detail = (JSON.parse(text) as { detail?: string }).detail ?? text;
  } catch {
    // JSON でなければそのまま
  }
  return new DataError(`${path} に失敗しました（HTTP ${response.status}）${detail ? `：${detail}` : ""}`, response.status);
}
