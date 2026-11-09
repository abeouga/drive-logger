// Cognito とのやりとり（ログイン・ログアウト・トークンの取り出し）。画面の部品はここを通してだけ使う。
// 方式：アプリの画面で入れたユーザー名・パスワードで、ユーザープールに直接ログインする（USER_SRP_AUTH。パスワードそのものは送らない）。
//       期限が切れたら更新用のトークンで取り直す（REFRESH_TOKEN_AUTH）。トークンは localStorage に置き、タブやブラウザを閉じても
//       更新用のトークンの期限（30 日、infra/cognito.tf）まではログインし直さずに使えるようにする（#63）。
import "./nodeGlobal"; // ライブラリより先に読み込む（中身はそのファイル）
import { AuthenticationDetails, CognitoUser, CognitoUserPool, type CognitoUserSession } from "amazon-cognito-identity-js";
import { readAuthConfig } from "./authConfig";

export interface SignedInUser {
  username: string;
}

export interface Credentials {
  username: string;
  password: string;
}

/** ログインできなかったとき。message はそのまま画面に出せる文。 */
export class SignInError extends Error {}

/** トークンの置き場所。ここだけで決める。 */
const TOKEN_STORAGE: Storage = window.localStorage;

let pool: CognitoUserPool | null = null;

function getPool(): CognitoUserPool {
  if (!pool) {
    const c = readAuthConfig();
    pool = new CognitoUserPool({ UserPoolId: c.userPoolId, ClientId: c.clientId, Storage: TOKEN_STORAGE });
  }
  return pool;
}

/**
 * ユーザー名・パスワードでログインする。失敗したら SignInError（理由の文付き）。
 * 引数なしで呼ぶと「ログインし直してもらう」：このブラウザのトークンを消し、読み直してログイン画面を出す（開いていた画面の #/ride/... は残る）。
 */
export async function signIn(credentials?: Credentials): Promise<void> {
  if (!credentials) {
    forgetTokens();
    window.location.reload();
    return;
  }
  const user = new CognitoUser({ Username: credentials.username.trim(), Pool: getPool(), Storage: TOKEN_STORAGE });
  const details = new AuthenticationDetails({ Username: credentials.username.trim(), Password: credentials.password });
  await new Promise<void>((resolve, reject) => {
    user.authenticateUser(details, {
      onSuccess: () => resolve(),
      onFailure: (err: unknown) => reject(new SignInError(reasonOf(err))),
      newPasswordRequired: () => reject(new SignInError("パスワードの変更が必要なユーザーです。管理者にパスワードを設定し直してもらってください")),
      mfaRequired: () => reject(new SignInError("このユーザーには追加の認証（MFA）が要ります。この画面は対応していません")),
      totpRequired: () => reject(new SignInError("このユーザーには追加の認証（MFA）が要ります。この画面は対応していません")),
      customChallenge: () => reject(new SignInError("この画面で扱えないログインの手順を求められました")),
    });
  });
}

/** ログアウトする：更新用のトークンを Cognito で無効にし（失敗しても続ける）、このブラウザのトークンを消す。画面の切り替えは呼んだ側がする。 */
export async function signOut(): Promise<void> {
  const user = getPool().getCurrentUser();
  if (!user) return;
  // 無効にできなかったとき（回線・更新用のトークンの期限切れなど）も、下で手元のトークンは消す
  await new Promise<void>((resolve) => user.signOut(() => resolve()));
  forgetTokens();
}

/** ログイン中のユーザー。いなければ（または期限切れで更新もできなければ）null。 */
export async function currentUser(): Promise<SignedInUser | null> {
  const session = await validSession();
  if (!session) return null;
  const payload = session.getIdToken().payload as Record<string, unknown>;
  const name = payload["cognito:username"] ?? getPool().getCurrentUser()?.getUsername() ?? payload.sub;
  return { username: String(name) };
}

/** API に付けるアクセストークン。いなければ null。 */
export async function accessToken(): Promise<string | null> {
  const session = await validSession();
  return session?.getAccessToken().getJwtToken() ?? null;
}

// ------------------------------------------------------------------ 内部

/** 有効なトークン。期限が切れていれば、ライブラリが更新用のトークンで取り直す（REFRESH_TOKEN_AUTH）。それもできなければ null。 */
async function validSession(): Promise<CognitoUserSession | null> {
  const user = getPool().getCurrentUser();
  if (!user) return null;
  return new Promise((resolve) => {
    user.getSession((err: Error | null, session: CognitoUserSession | null) => {
      resolve(!err && session?.isValid() ? session : null);
    });
  });
}

/** このブラウザに置いたトークンを消す（Cognito には問い合わせない）。 */
function forgetTokens(): void {
  getPool().getCurrentUser()?.signOut();
}

/** Cognito の失敗を、画面に出す文にする。 */
function reasonOf(err: unknown): string {
  const code = (err as { code?: string; name?: string } | null)?.code ?? (err as { name?: string } | null)?.name ?? "";
  switch (code) {
    case "NotAuthorizedException":
    case "UserNotFoundException":
      return "ユーザー名かパスワードが違います";
    case "PasswordResetRequiredException":
      return "パスワードの設定し直しが必要です。管理者に連絡してください";
    case "UserNotConfirmedException":
      return "このユーザーはまだ使えるようになっていません。管理者に連絡してください";
    case "TooManyRequestsException":
    case "LimitExceededException":
      return "ログインの試行が多すぎます。しばらく待ってからやり直してください";
    case "NetworkError":
      return "Cognito につながりませんでした。回線を確かめてください";
    default:
      return `ログインできませんでした：${(err as Error | null)?.message ?? String(err)}`;
  }
}
