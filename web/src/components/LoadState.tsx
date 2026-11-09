// 読み込み中・失敗の表示（dev で動かしているときの案内も出す）
export default function LoadState({ error, label = "データ" }: { error: string | null; label?: string }) {
  if (!error) return <div role="status" className="notice">{label}を読み込み中…</div>;
  return (
    <div role="alert" className="notice notice-danger">
      <div className="font-semibold">{label}を読み込めませんでした</div>
      <div className="text-xs break-all">{error}</div>
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
