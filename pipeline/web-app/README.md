# web-app（CT125 走行データの Web アプリ版）

React ＋ TypeScript ＋ Vite ＋ Tailwind の静的 SPA。`vite-plugin-singlefile` で `dist/index.html` 1 ファイルにまとめ、S3 の署名付き URL で配る（`docs/WEB_PLAN.md`）。

## 手順（リポジトリのルートから）

データを書き出す（自宅マスクと 300 m の検査つき）：

```bash
.venv/Scripts/python.exe -m ct125 export
```

依存を入れる（初回だけ）：

```bash
npm --prefix web-app install
```

開発サーバー：

```bash
npm --prefix web-app run dev
```

1 ファイルにビルドする：

```bash
npm --prefix web-app run build
```

ビルド後のファイルに自宅周辺の座標がないか検査する：

```bash
.venv/Scripts/python.exe -m ct125 check-privacy web-app/dist/index.html
```

`src/data/`（書き出したデータ）と `dist/` はコミットしない。
