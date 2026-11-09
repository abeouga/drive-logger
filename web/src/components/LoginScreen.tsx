// ログイン前の画面。ユーザー名とパスワードをこの画面で入れてログインする（Cognito の画面へは移らない）。
// 形と大きさは文之助のログイン画面（幅 380px のカード・高さ 44px の入力欄・高さ 46px のボタン）にそろえる。色は役割の色、部品は index.css の形を使う。
import { useState, type FormEvent } from "react";
import type { Credentials } from "../lib/auth/authClient";

interface Props {
  /** 画面を開いたときから出しておく知らせ（前のログインの確かめに失敗した理由など） */
  notice?: string;
  /** ログインする。失敗したら理由の文を持つ Error を投げる */
  onSignIn: (credentials: Credentials) => Promise<void>;
}

const fieldClass = "grid gap-1.5 text-[13px] font-bold text-ink-2";
// 部品の形は index.css の field・btn btn-primary。ログイン画面だけの大きさ（入力欄 44px・ボタン 46px）を足す
const inputClass = "field h-11 rounded-lg text-base font-normal outline-none disabled:opacity-60";

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
          <p role="alert" className="m-0 text-[13px] text-critical">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="btn btn-primary mt-1 h-[46px] w-full text-[15px]"
        >
          {busy ? "ログイン中…" : "ログイン"}
        </button>
      </form>
    </main>
  );
}
