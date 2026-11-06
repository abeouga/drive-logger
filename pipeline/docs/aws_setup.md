# AWS 最小構成の手順（フェーズ 4）

目的：データ（raw / processed）と走行ページ（site）を S3 に置き、人に見せられる **署名付き URL** を用意する。バケットは公開しない。

> 状態（2026-11-06）：コードと手順は用意済み。**バケットはまだ作っていない**（本人の確認待ち：プロファイル・リージョン・バケット名）。

## 0. 前提

- この AWS は「新しい AWS 体験」のプロジェクト。リージョンはプロジェクトごとに固定で、**AWS Settings > View all projects > Overview > Additional Info > Region** で確認する。`~/.aws/config` では `fuminosuke`（`aws login` のセッション）と `fuminosuke-deploy` が `ap-southeast-2` になっており、計画書の `ap-northeast-1` とは違う。**コードはリージョンを決め打ちせず、プロファイルの region を使う。**
- 認証は `aws login`（プロファイル `fuminosuke`）。セッションが切れたら `aws login --profile fuminosuke`。
- 使うのは S3 だけ。料金は無料枠内に収まる見込み（データ約 100 MB、GET はごくわずか）。

## 1. 設定

`config/default.yaml` の `aws` または `config/local.yaml` の `aws`（コミットしない）：

```yaml
aws:
  profile: fuminosuke
  bucket: ct125-logger-xxxxxx   # 小文字・数字・ハイフン。世界で一意になるよう接尾辞を付ける
```

## 2. バケット作成（1 回だけ）

```bash
.venv/Scripts/python.exe -m ct125 bucket
```

やること：`create_bucket`（プロファイルのリージョン）→ パブリックアクセスブロック 4 項目を有効 → 既定の暗号化 SSE-S3。既にあれば何もしない。

## 3. アップロード

**先に自宅マスクを適用する**：`config/local.yaml` に `home: {lat, lon}` を書き、`process --all` → `score` → `render` を再実行。`local.yaml` がない状態では `upload` は `processed/` と `site/` を拒否する（`raw/` だけなら通る。`raw/` も位置情報を含むので、公開しないバケットにだけ置く）。

```bash
.venv/Scripts/python.exe -m ct125 upload
```

```bash
.venv/Scripts/python.exe -m ct125 upload --ride ride_004 --ride ride_005 --parts processed,site,models
```

バケットの中：

```
raw/<ride_id>/{accel.csv,gps.csv,events.csv,status.csv,meta.json}
processed/<ride_id>/{windows.parquet,scored.parquet}
models/<yyyymmdd>/{baseline.json,isolation_forest.pkl}
site/<ride_id>/index.html
```

## 4. 署名付き URL の発行

```bash
.venv/Scripts/python.exe -m ct125 share --ride ride_004 --ride ride_005 --expires-hours 72
```

- 上限は 7 日（168 時間）。
- **重要**：`aws login` の一時認証情報（assumed role）で発行した URL は、`--expires-hours` に関係なく **その一時認証情報の期限（数時間〜最長 12 時間程度）で失効する**。確実に開くには次のどちらか：
  1. **見せる当日の朝に発行し直す**（推奨。`aws login` してから `share`）。前日の発行だけでは足りない可能性がある
  2. 長期の認証情報（IAM ユーザーのアクセスキー）を持つプロファイルで発行する。その場合そのユーザーの権限はこのバケットの `s3:GetObject` だけに絞る
- URL はスマホのブラウザで開いて地図が出ることを確認する（地図タイルは OpenStreetMap から読む。Plotly は CDN）。
- URL をチャットやメールで送ると、その相手は期限内なら誰でも開ける。見せる相手にだけ渡す。

## 5. 権限（最小）

このバケットだけに `s3:PutObject`・`s3:GetObject`・`s3:ListBucket`（`bucket` コマンドには `s3:CreateBucket`・`s3:PutBucketPublicAccessBlock`・`s3:PutEncryptionConfiguration` も）。「新しい AWS 体験」では人の権限は AWS が管理しているので、通常は追加のロール作成は不要。専用の IAM ユーザーを作る場合だけ上記のポリシーを付ける。

## 6. 静的ウェブサイトホスティング（Should、やらない既定）

やる場合は `site/` だけを別バケットにして CloudFront + OAC で配信する（バケット自体は公開しない）。本人の確認後に着手。CloudFront は us-east-1 の WAF 等に依存するので、このプロジェクトでは署名付き URL を既定にする。

## 7. 片付け

不要になったら、バケットのオブジェクトを消してからバケットを削除する（本人が確認してから実行）。
