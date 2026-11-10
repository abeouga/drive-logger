// ログインの設定。値は .env.production.local（公開版。scripts/deploy.ps1 が Terraform の出力から作る）か、
// dev では .env.development.local（scripts/start-dev.ps1 が Terraform の出力から作る）→ .env.development（コミット済み）の順に入る。
// どれも秘密ではない（ブラウザに見えてよい値）。
export interface AuthConfig {
  /** ユーザープール ID（<region>_<文字列>） */
  userPoolId: string;
  /** Cognito のアプリクライアント ID（シークレットなし） */
  clientId: string;
}

export function readAuthConfig(): AuthConfig {
  const authority = required("VITE_AUTH_AUTHORITY", import.meta.env.VITE_AUTH_AUTHORITY);
  return {
    userPoolId: userPoolIdOf(authority),
    clientId: required("VITE_AUTH_CLIENT_ID", import.meta.env.VITE_AUTH_CLIENT_ID),
  };
}

/** 発行元 https://cognito-idp.<region>.amazonaws.com/<ユーザープール ID> から、ユーザープール ID を取り出す。 */
function userPoolIdOf(authority: string): string {
  const id = authority.replace(/\/+$/, "").split("/").pop() ?? "";
  if (!/^[a-z0-9-]+_[A-Za-z0-9]+$/.test(id)) throw new Error(`VITE_AUTH_AUTHORITY からユーザープール ID を読めません：${authority}`);
  return id;
}

function required(name: string, value: string | undefined): string {
  if (!value) throw new Error(`${name} が設定されていません（公開版は scripts/deploy.ps1、dev は scripts/start-dev.ps1 で起動してください）`);
  return value;
}
