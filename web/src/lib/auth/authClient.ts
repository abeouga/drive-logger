// Cognito とのやりとり（ログイン・ログアウト・トークンの取り出し）。画面の部品はここを通してだけ使う。
// 方式は認可コード＋PKCE（oidc-client-ts）。トークンはタブを閉じると消える sessionStorage に置く。
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import { readAuthConfig, type AuthConfig } from "./authConfig";

export interface SignedInUser {
  username: string;
}

let config: AuthConfig | null = null;
let manager: UserManager | null = null;

function getConfig(): AuthConfig {
  config ??= readAuthConfig();
  return config;
}

function getManager(): UserManager {
  manager ??= createManager(getConfig());
  return manager;
}

function createManager(c: AuthConfig): UserManager {
  return new UserManager({
    authority: c.authority,
    client_id: c.clientId,
    redirect_uri: c.returnUrl,
    response_type: "code",
    scope: "openid",
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: true,
    extraQueryParams: { lang: "ja" }, // ログイン画面を日本語にする
  });
}

/** Cognito のログイン画面へ移る。戻ってきたら今の画面（#/ride/... など）に戻す。 */
export async function signIn(): Promise<void> {
  await getManager().signinRedirect({ state: window.location.hash });
}

/** このブラウザのトークンを消し、Cognito 側のログインも終わらせる。 */
export async function signOut(): Promise<void> {
  await getManager().removeUser();
  window.location.assign(logoutUrl(getConfig()));
}

/** ログイン画面から戻ってきたところなら、コードをトークンに換える。そうでなければ何もしない。 */
export async function completeSignInIfReturning(): Promise<void> {
  if (!isReturningFromLogin()) return;
  const user = await getManager().signinRedirectCallback();
  restoreScreen(user);
}

/** ログイン中のユーザー。いなければ（または期限切れで更新もできなければ）null。 */
export async function currentUser(): Promise<SignedInUser | null> {
  const user = await validUser();
  return user ? { username: usernameOf(user) } : null;
}

/** API に付けるアクセストークン。いなければ null。 */
export async function accessToken(): Promise<string | null> {
  const user = await validUser();
  return user?.access_token ?? null;
}

// ------------------------------------------------------------------ 内部

async function validUser(): Promise<User | null> {
  const user = await getManager().getUser();
  if (user && !user.expired) return user;
  if (user?.refresh_token) return renew();
  return null;
}

async function renew(): Promise<User | null> {
  try {
    return await getManager().signinSilent();
  } catch {
    return null; // 更新用のトークンも切れていたら、ログインし直してもらう
  }
}

function isReturningFromLogin(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.has("code") && params.has("state");
}

/** URL から ?code=... を消し、ログイン前の画面（ハッシュ）に戻す。 */
function restoreScreen(user: User): void {
  const hash = typeof user.state === "string" ? user.state : "";
  window.history.replaceState(null, "", `/${hash}`);
}

function usernameOf(user: User): string {
  const profile = user.profile as Record<string, unknown>;
  const name = profile["cognito:username"] ?? profile["username"] ?? profile.sub;
  return String(name);
}

/** Cognito のログアウト URL（Cognito は OIDC 標準のログアウトに対応していないので、専用の形で組み立てる）。 */
function logoutUrl(c: AuthConfig): string {
  const params = new URLSearchParams({ client_id: c.clientId, logout_uri: c.returnUrl });
  return `${c.loginDomain}/logout?${params.toString()}`;
}
