# ローカルで動かす

## 初回

```bash
npm install
```

`.env.example` を `.env.local` にコピーして値を入れる（`S3_BUCKET` は ct125-logger-terraform の `terraform output bucket_name`）。

## ふだん（S3 から読む）

`.env.local` を `DATA_SOURCE=s3` にして：

```bash
npm run dev
```

http://localhost:5173 を開く。起動時のログに `データの出どころ: s3://…/app/v1/（プロファイル ct125-logger）` と出る。

- ブラウザは `/data/<ファイル名>` を取りにいき、dev サーバー（`server/s3-data.ts`）が `~/.aws` のプロファイルで S3 から取って返す。取ったものは `cache/` にも保存する
- AWS の認証情報・バケット名はブラウザに渡らない（`.env.local` の変数に `VITE_` を付けないこと）
- dev サーバーは localhost だけで待ち受ける。`--host` は付けない（同じ Wi-Fi の端末から S3 の中身が見えてしまう）

### データを新しくする

ct125-logger で書き出して S3 に上げ、ブラウザを再読み込みする：

```bash
.venv/Scripts/python.exe -m ct125 export --upload
```

## 回線なし・S3 を使わない（cache モード）

`.env.local` を `DATA_SOURCE=cache` にして `npm run dev`。`cache/` だけを読む。

`cache/` の作り方は 2 通り：

- S3 から写す：`scripts/pull-data.ps1`（S3 に `rides.json` がないときは何もしない）
- S3 を通さず ct125-logger から直接書き出す：

```bash
.venv/Scripts/python.exe -m ct125 export --out D:/ct125-app/cache
```

## 配布用の 1 ファイルを作る

```powershell
scripts\build-single.ps1
```

S3 から `cache/` を更新 → `npm run build`（`cache/` のデータを HTML に埋め込む）→ ct125-logger の `check-privacy` で自宅周辺の座標がないか検査、の順に行う。今の `cache/` のままビルドするなら `-NoPull`。

できた `dist/index.html` を S3 に上げて URL を出す（ct125-logger で）：

```bash
.venv/Scripts/python.exe -m ct125 upload --site-app D:/ct125-app/dist/index.html
```

```bash
.venv/Scripts/python.exe -m ct125 share --app --expires-hours 72
```

## 困ったとき

| 症状 | 原因と対処 |
|---|---|
| 「走行一覧を読み込めませんでした（HTTP 502）」 | AWS の認証切れ。プロファイル `ct125-logger` の鍵を確認（`aws sts get-caller-identity --profile ct125-logger`）。`cache/` に前のデータがあれば、それを返して画面は出る（レスポンスヘッダー `X-Data-Source: cache-fallback`） |
| 「…がありません（HTTP 404）」 | S3 の `app/v1/` にまだ上げていない。ct125-logger で `export --upload` |
| dev サーバーが起動時に止まる「S3_BUCKET が未設定」 | `.env.local` を作っていない／`<アカウントID>` のまま |
| `npm run build` が「cache/rides.json がありません」で止まる | 先に `scripts/pull-data.ps1`（または `export --out D:/ct125-app/cache`） |
| 地図が出ない | 回線（OpenFreeMap のタイル）を確認。地図の枠の上にエラーの内容が出る |
| 地図をホイールで拡大できない | Ctrl（Mac は ⌘）を押しながらホイール。ページのスクロールを妨げないため |
