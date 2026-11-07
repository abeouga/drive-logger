// ログインの設定。値はビルド時に .env.production.local から入る（scripts/deploy.ps1 が Terraform の出力から作る）。
// どれも秘密ではない（ブラウザに見えてよい値）。
export interface AuthConfig {
  /** OIDC の発行元：https://cognito-idp.<region>.amazonaws.com/<ユーザープール ID> */
  authority: string;
  /** Cognito のアプリクライアント ID（シークレットなし） */
  clientId: string;
  /** ログイン画面のドメイン：https://<prefix>.auth.<region>.amazoncognito.com（ログアウトで使う） */
  loginDomain: string;
  /** ログイン後・ログアウト後に戻ってくる URL（このサイトのトップ） */
  returnUrl: string;
}

export function readAuthConfig(): AuthConfig {
  return {
    authority: required("VITE_AUTH_AUTHORITY", import.meta.env.VITE_AUTH_AUTHORITY),
    clientId: required("VITE_AUTH_CLIENT_ID", import.meta.env.VITE_AUTH_CLIENT_ID),
    loginDomain: required("VITE_AUTH_DOMAIN", import.meta.env.VITE_AUTH_DOMAIN),
    returnUrl: `${window.location.origin}/`,
  };
}

function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} が設定されていません（scripts/deploy.ps1 でビルドしてください）`);
  return value;
}
