# AWS 最小構成の手順（フェーズ 4）

目的：データ（raw / processed / models）と走行ページ（site）を S3 に置き、人に見せられる **署名付き URL** を用意する。バケットは公開しない。

> 状態（2026-11-06）：バケットを Terraform で作成済み（東京 ap-northeast-1）。`models/` だけアップロード済み。`raw/`・`processed/`・`site/` は **自宅マスク適用後** に上げる。

## 0. 前提

- アカウント：ct125-logger 専用の AWS アカウント。CLI プロファイル **`ct125-logger`**（IAM ユーザーの長期アクセスキー、region = ap-northeast-1）。プラン：有料（PAID）。
- リージョン：「新しい AWS 体験」ではプロジェクトごとに固定。読み取り API ではどのリージョンも拒否されず判定できなかったため、住所（熊本）と計画書から **ap-northeast-1** とし、そこでバケット作成が通った。念のため **AWS Settings > View all projects > Overview > Additional Info > Region** で確認する。
- 鍵はリポジトリにも Terraform フォルダーにも置かない（`~/.aws/credentials` のみ）。
- 使うのは S3 だけ。データ約 100 MB で、料金は月数円〜数十円の見込み。

## 1. バケットの作成（Terraform、済み）

Terraform は `D:\ct125-logger-terraform`（このリポジトリの外。state はそのフォルダーのローカル）。

```bash
terraform -chdir=D:/ct125-logger-terraform plan
```

```bash
terraform -chdir=D:/ct125-logger-terraform apply
```

作るもの：バケット `ct125-logger-<アカウントID>`、パブリックアクセスブロック 4 項目、BucketOwnerEnforced（ACL 無効）、SSE-S3、HTTPS 以外を拒否するバケットポリシー、バージョニング（古い版は 30 日で削除）。IAM は作らない。

（`python -m ct125 bucket` は Terraform を使わない場合の予備。Terraform 管理のバケットには使わない。）

## 2. 設定

`config/local.yaml`（コミットしない）：

```yaml
aws:
  profile: ct125-logger
  bucket: ct125-logger-<アカウントID>   # terraform output bucket_name
home:                                   # 自宅マスク。書くまで processed/ と site/ は上げられない
  lat: …
  lon: …
```

## 3. アップロード

**先に自宅マスクを適用する**：`config/local.yaml` に `home` を書き、`process --all` → `score` → `render` を再実行。`home` がない状態では `upload` は `processed/` と `site/` を拒否する（終了コード 2）。

```bash
.venv/Scripts/python.exe -m ct125 upload
```

一部だけ：

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

- 上限は 7 日（168 時間）。`ct125-logger` プロファイルは長期キーなので、指定した期限まで有効。
- 見せる前日に 72 時間で発行すれば、翌日まで十分に覆う。
- **アクセスキーを無効化・削除すると、そのキーで発行した URL はすべて開けなくなる。** キーをローテーションするなら、新しいキーに切り替えてから URL を発行する。
- スマホのブラウザで開いて地図が出ることを確認する（地図タイルは OpenStreetMap、Plotly は CDN から読む）。
- URL を知っている人は期限内なら誰でも開ける。見せる相手にだけ渡す。

## 5. 権限と鍵の扱い（ベストプラクティス）

- 長期のアクセスキーは漏れると期限なく使われる。チャットなどに貼った鍵は **ローテーション**（新しいキーを作って `aws configure --profile ct125-logger` で差し替え、古いキーを削除）する。
- 普段の操作は短期の認証情報（`aws login`）が望ましい。ただし短期の認証情報で発行した署名付き URL はその認証情報の期限（数時間）で失効するので、人に渡す URL の発行にだけ長期キーを使う、という分け方がよい。
- `CubLoger-deploy-user` の権限は、可能ならこのバケットへの `s3:PutObject`・`s3:GetObject`・`s3:ListBucket` と Terraform が使う S3 の設定系に絞る。

## 6. 静的ウェブサイトホスティング（Should、やらない既定）

やる場合は `site/` だけを別バケットにして CloudFront + OAC で配信する（バケット自体は公開しない）。本人の確認後に着手。

## 7. 片付け

**方針（2026-11-06 本人決定）：バケットは当面残す。** 残すか消すかは後で改めて決める。

バケットは `force_destroy = false`（中身があると `terraform destroy` が失敗し、生データの誤削除を防ぐ）。消すときは本人が確認してから、全バージョンを削除 → `terraform destroy`。
