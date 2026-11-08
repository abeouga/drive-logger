// 読み込み中・失敗の表示（dev で動かしているときの案内も出す）
export default function LoadState({ error, label = "データ" }: { error: string | null; label?: string }) {
  if (!error) return <div className="rounded-lg border border-line bg-surface p-4 text-sm text-ink-2">{label}を読み込み中…</div>;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4 text-sm">
      <div className="font-semibold">{label}を読み込めませんでした</div>
      <div className="text-xs break-all text-ink-2">{error}</div>
      {import.meta.env.DEV && (
        <div className="text-xs leading-relaxed text-ink-2">
          開発サーバーで動かしている場合：<code>npm run dev</code> は公開ドメインのデータ API に中継します（ログインが要ります）。
          <code>npm run dev:local</code> のときは、手元のデータ API（<code>http://localhost:8000</code>）が動いているか、
          その AWS の認証が切れていないかを確認してください（<code>docs/local_dev.md</code>）。
        </div>
      )}
    </div>
  );
}
