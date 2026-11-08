# CT125 の AWS リソース（Terraform）

ハンターカブ CT125 走行データロガーの AWS リソース一式。

- データを作る側：`pipeline/`（解析パイプライン。S3 にデータを上げる）
- データを見る側：`web/`・`api/`（Web アプリ＋データ API。https://drive.herdio-system.com/ ）

## state の置き場

state は S3（`ct125-logger-tfstate-535562976288` の `infra/terraform.tfstate`、ap-northeast-1）に置き、S3 だけでロックする（`versions.tf` の `backend "s3"`）。
どの PC でも `terraform init` すれば同じ state を使う。バケットは Terraform の外で作った（非公開・SSE-S3・HTTPS のみ・バージョニング）。
別の PC での準備は [docs/setup_another_pc.md](../docs/setup_another_pc.md)。

## 作るもの

| ファイル | リソース | 内容 |
|---|---|---|
| `s3.tf` | S3 バケット `ct125-logger-<アカウントID>` | 非公開・SSE-S3・HTTPS のみ・バージョニング。CloudFront には `webapp/` だけ読ませる |
| `certificate.tf` | ACM 証明書（**us-east-1**） | `drive.herdio-system.com`。CloudFront 用なので us-east-1 に置く決まり |
| `cognito.tf` | Cognito ユーザープール・アプリクライアント・ログイン画面 | 新規登録は不可。認可コード＋PKCE |
| `cognito_users.tf` | ログインできるユーザー | `terraform.tfvars` の `app_users` と `app_user_passwords` どおりに作る |
| `data_api.tf` | API Gateway（HTTP API）・Lambda・IAM ロール・ログ | `/api/health` 以外は JWT が必要。Lambda は `app/v1/datasets/*` だけ読める |
| `cloudfront.tf` | CloudFront・OAC | `/*` → S3 `webapp/`、`/api/*` → API Gateway |
| `ride_pipeline.tf` | ECR・Lambda（コンテナ）・IAM ロール・S3 イベント | `raw/<走行>/upload_complete.json` で前処理 → 推論 → 書き出し。手動で `{"action":"retrain"}` |
| `device_api.tf` | Lambda（デバイス API）・IAM ロール・API Gateway の POST ルート | ESP32 が生データを `raw/` に直接置くための受付。権限は raw/ に置くことと機器トークンのハッシュを読むことだけ |

## 前提

- AWS CLI のプロファイル `ct125-logger`（鍵はこのフォルダーに置かない）
- リージョンは「新しい AWS 体験」のプロジェクトで固定（`ap-northeast-1`）。AWS Settings > View all projects > Overview > Additional Info > Region で確認
- `terraform.tfvars`（コミットしない）：`example.tfvars` をコピーして、ユーザー名とパスワードを書く
- データ API の zip：`api/scripts/build-lambda.ps1` で `api/dist/lambda.zip` を作っておく
- 走行データ処理のコンテナ：初回は ECR を先に作ってからイメージを上げる
  1. `terraform apply -target=aws_ecr_repository.pipeline`
  2. `pipeline/scripts/build-pipeline-image.ps1`（`pipeline_image.auto.tfvars` に digest を書く。書き換わったらコミットする）
  3. `terraform apply`
- マスクする地点：`pipeline/` で `python -m ct125 sync-private-points`（SSM の `/ct125/private-points`。Terraform は値を持たない）
- モデルの版：S3 の `models/current.json`（`{"version": "..."}`）。retrain が書き換える
- DNS は Cloudflare（`herdio-system.com`）。次の 2 つの CNAME を **プロキシなし（DNS のみ）** で置く
  - 証明書の確認用：`terraform output certificate_validation_record`
  - 公開用：`drive` → `terraform output cloudfront_domain`

## 使い方

```bash
terraform init
```

```bash
terraform plan
```

```bash
terraform apply
```

apply の後、画面を出すのは `D:\ct125-app\scripts\deploy.ps1`（Terraform の出力からログイン設定を作り、ビルドして S3 に上げる）。

## destroy して作り直すとき

- ユーザー・パスワードは `terraform.tfvars` から自動で戻る。ユーザープール ID とクライアント ID は変わるが、`deploy.ps1` が毎回 Terraform の出力から読むので、デプロイし直せば画面も追従する
- CloudFront のドメイン（`xxxx.cloudfront.net`）は変わるので、Cloudflare の `drive` の CNAME を直す
- S3 バケットは中身があると消えない（`force_destroy = false`）。生データを誤って消さないための意図的な設定。アプリ部分だけ消すなら `-target` で指定する

## 注意

- state にはユーザーのパスワードとアカウント ID が入る。S3 のバケットを公開しない・コミットしない
- パスワードの決まりは緩めてある（8 文字以上・英小文字と数字）。後で `cognito.tf` の `password_policy` を 12 文字以上・英大文字必須に戻し、パスワードも変える
