// データファイルの取り出し口。起動のしかた（DATA_MODE）によって「どこから・どう取るか」だけが変わる。
//   dev      : /data/<名前>      … Vite の dev サーバー（server/s3-data.ts）が S3 から返す。ログインなし
//   hosted   : /api/data/<名前>  … データ API（ログインが必要）。アクセストークンを付ける
import { accessToken, signIn } from "./auth/authClient";

declare const __DATA_MODE__: "dev" | "hosted"; // vite.config.ts の define

export const DATA_MODE = __DATA_MODE__;

export class DataError extends Error {}

/** データファイルを取ってくる。失敗したら DataError。 */
export async function fetchDataFile(name: string): Promise<Response> {
  const response = DATA_MODE === "hosted" ? await fetchFromApi(name) : await fetchFromDevServer(name);
  if (!response.ok) throw await errorFrom(name, response);
  return response;
}

async function fetchFromDevServer(name: string): Promise<Response> {
  return fetch(`/data/${name}`, { cache: "no-store" });
}

async function fetchFromApi(name: string): Promise<Response> {
  const token = await accessToken();
  if (!token) return redirectToLogin();
  const response = await fetch(`/api/data/${name}`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
  if (response.status === 401) return redirectToLogin();
  return response;
}

/** ログインが切れていたら、ログイン画面へ移る（この後の処理は続かない）。 */
async function redirectToLogin(): Promise<never> {
  await signIn();
  throw new DataError("ログインし直しています");
}

async function errorFrom(name: string, response: Response): Promise<DataError> {
  const detail = (await response.text()).slice(0, 300);
  return new DataError(`${name} を取得できませんでした（HTTP ${response.status}）${detail ? `：${detail}` : ""}`);
}
