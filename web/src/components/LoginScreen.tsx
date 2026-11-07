// ログイン前の画面。ボタンを押すと Cognito のログイン画面へ移る。
export default function LoginScreen({ error, onSignIn }: { error?: string; onSignIn: () => Promise<void> }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 text-ink">
      <div className="w-full max-w-sm rounded-lg border border-line bg-surface p-6">
        <h1 className="text-lg font-semibold tracking-tight">CT125 走行データ</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          ハンターカブ CT125 の走行データ（GPS と振動）を、地図とタイムラインで見るアプリです。見るにはログインしてください。
        </p>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <button
          type="button"
          onClick={() => void onSignIn()}
          className="mt-5 w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          ログイン
        </button>
      </div>
    </div>
  );
}
