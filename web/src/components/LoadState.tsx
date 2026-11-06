// 読み込み中・失敗の表示（dev で S3 の認証が切れたときの案内も出す）
export default function LoadState({ error, label = "データ" }: { error: string | null; label?: string }) {
  if (!error) return <div className="rounded-lg border border-line bg-surface p-4 text-sm text-ink-2">{label}を読み込み中…</div>;
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4 text-sm">
      <div className="font-semibold">{label}を読み込めませんでした</div>
      <div className="text-xs break-all text-ink-2">{error}</div>
      {import.meta.env.DEV && (
        <div className="text-xs leading-relaxed text-ink-2">
          開発サーバーで動かしている場合：AWS の認証が切れていないか（<code>aws login --profile ct125-logger</code> 等）、
          <code>.env.local</code> の <code>S3_BUCKET</code>・<code>S3_PREFIX</code> が正しいか、S3 の <code>app/v1/</code> にデータがあるかを確認してください。
          回線なしで触るときは <code>DATA_SOURCE=cache</code>（<code>docs/local_dev.md</code>）。
        </div>
      )}
    </div>
  );
}
