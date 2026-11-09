# ローカルで動かす

画面はどの起動のしかたでも、データ API（`/api/*`）からだけデータを読む。S3 を直接読むコードは無い。

| 起動 | `/api/*` の中継先 | ログイン | 使う場面 |
|---|---|---|---|
| `npm run dev`（`start.bat`） | 公開ドメイン（https://drive.herdio-system.com） | 要る（公開版と同じ Cognito） | ふだん。公開版と同じデータ・同じ権限で見る |
| `npm run dev:local` | 手元で動かしたデータ API（http://localhost:8000） | 要らない（手元の開発者＝admin） | API と画面を一緒に直すとき |

## いちばん簡単な起動（ダブルクリック）

このフォルダーの `start.bat`（リポジトリの直下の `start.bat` でも同じ）をダブルクリックする。中身は `scripts/start-dev.ps1` で、

1. すでに起動していれば、ブラウザで http://localhost:5173 を開くだけ
2. 初回は `npm install`
3. ログインの設定（`.env.development.local`）を Terraform の出力から作る（公開版の `deploy.ps1` と同じ値。秘密ではない）
4. dev サーバーを起動し、準備ができたらブラウザを開く

止めるときは黒い画面で Ctrl+C（「バッチ ジョブを終了しますか」には Y）。ブラウザを開かずに起動するときは `start.bat -NoBrowser`。

## ふだん（公開ドメインのデータ API を使う）

```bash
npm run dev
```

http://localhost:5173 を開き、公開版と同じユーザーでログインする。

- ログインはアプリの画面で、ユーザープールに直接する（USER_SRP_AUTH。パスワードそのものは送らない）。Cognito の画面へは移らないので、戻り先の URL には左右されない
- トークンはタブごとの sessionStorage に置く。タブを閉じるとログインし直し
- admin でログインすると「この走行を消す」「ゴミ箱」「この結果に戻す」「このモデルに切り替える」が出る。**本番のデータが変わる**ので、確かめるときは戻せる操作（消す → 戻す など）だけにする

## 手元のデータ API につなぐ（ログインなし）

API と画面を一緒に直すときは、データ API を手元で動かす。`ALLOW_LOCAL_USER=true` で、ログインなしの「手元の開発者」（admin）として扱われる。

```powershell
cd api
$env:AWS_PROFILE="ct125-logger"; $env:DATA_BUCKET="ct125-logger-public-<アカウントID>"; $env:WORK_BUCKET="ct125-logger-work-<アカウントID>"; $env:PIPELINE_FUNCTION="ct125-ride-pipeline"; $env:ALLOW_LOCAL_USER="true"
uv run uvicorn ct125_api.main:app --port 8000 --app-dir src
```

別の画面で：

```bash
npm run dev:local
```

- 手元のデータ API も本番のバケットを読み書きする（台帳を書き換え、処理の Lambda に公開を頼む）。admin の操作は本番に効く
- `ALLOW_LOCAL_USER` は手元だけで使う。Lambda では必ず付けない（Terraform は設定しない）

## データを新しくする

画面用のデータを書くのは、AWS の処理の Lambda だけ。走行を足すときは機器から送る（PC からは `python -m ct125 upload-sd`）。
全走行を作り直すときは、Lambda に `{"action": "retrain"}` を渡す（`pipeline/README.md`）。終わったらブラウザを再読み込みする。

## 困ったとき

| 症状 | 原因と対処 |
|---|---|
| 起動時に「VITE_AUTH_AUTHORITY が設定されていません」 | `start.bat`（`scripts/start-dev.ps1`）で起動する。Terraform の出力からログインの設定を作る |
| `npm run dev:local` で「走行一覧を読み込めませんでした」 | 手元のデータ API（http://localhost:8000）が動いているか、その AWS の認証が切れていないか（`aws sts get-caller-identity --profile ct125-logger`） |
| 「…がありません（HTTP 404）」 | 公開用のバケットの `datasets/shared/` にまだ無い。処理の Lambda（`ct125-ride-pipeline`）のログを確かめる |
| 地図が出ない | 回線（OpenFreeMap のタイル）を確認。地図の枠の上にエラーの内容が出る |
| 地図をホイールで拡大できない | Ctrl（Mac は ⌘）を押しながらホイール。ページのスクロールを妨げないため |
