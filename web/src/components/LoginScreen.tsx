// ログイン前の画面。ユーザー名とパスワードをこの画面で入れてログインする（Cognito の画面へは移らない）。
// 形と大きさは文之助のログイン画面（幅 380px のカード・高さ 44px の入力欄・高さ 46px のボタン）にそろえる。色は役割の色を使う。
import { useState, type FormEvent } from "react";
import type { Credentials } from "../lib/auth/authClient";

interface Props {
  /** 画面を開いたときから出しておく知らせ（前のログインの確かめに失敗した理由など） */
  notice?: string;
  /** ログインする。失敗したら理由の文を持つ Error を投げる */
  onSignIn: (credentials: Credentials) => Promise<void>;
}

const fieldClass = "grid gap-1.5 text-[13px] font-bold text-ink-2";
const inputClass =
  "h-11 rounded-lg border border-[var(--border-strong,#b7c5d2)] bg-surface px-3 text-base font-normal text-ink outline-none " +
  "focus:border-accent focus:shadow-[0_0_0_3px_var(--accent-wash)] disabled:opacity-60";

export default function LoginScreen({ notice, onSignIn }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(notice ?? "");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await onSignIn({ username, password });
    } catch (e) {
      setError((e as Error).message);
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-page px-4 py-6 text-ink">
      <form
        onSubmit={(e) => void submit(e)}
        aria-labelledby="login-title"
        className="grid w-full max-w-[380px] gap-4 rounded-2xl border border-line bg-surface px-8 pt-9 pb-8 shadow-[0_18px_48px_#1632471a]"
      >
        <h1 id="login-title" className="mb-1 text-center text-2xl font-extrabold tracking-[.04em]">
          ドライブロガー ログイン
        </h1>
        <label className={fieldClass}>
          <span>ユーザー名</span>
          <input
            className={inputClass}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            disabled={busy}
          />
        </label>
        <label className={fieldClass}>
          <span>パスワード</span>
          <input
            className={inputClass}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
        </label>
        {error && (
          <p role="alert" className="m-0 text-[13px] text-[var(--critical)]">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="mt-1 h-[46px] w-full rounded-[10px] border border-[var(--accent-dark,#18547e)] bg-accent text-[15px] font-bold text-white hover:bg-[var(--accent-dark,#18547e)] disabled:cursor-not-allowed disabled:opacity-55"
        >
          {busy ? "ログイン中…" : "ログイン"}
        </button>
      </form>
    </main>
  );
}
