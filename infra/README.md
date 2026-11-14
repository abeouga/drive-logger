# CT125 の AWS リソース（Terraform）

ハンターカブ CT125 走行データロガーの AWS リソース一式。

- データを作る側：`pipeline/`（解析パイプライン。S3 にデータを上げる）
- データを見る側：`web/`・`api/`（Web アプリ＋データ API。https://drive.herdio-system.com/ ）

## 環境（本番と test）

同じ Terraform で本番（prod）と test を作る。名前は `environment.tf` で `env` から作り、本番は今の名前のまま、test は `ct125-test-…` になる。
本番は workspace の `default` と `terraform.tfvars`、test は workspace の `test` と `-var-file=test.tfvars -var-file=pipeline_image.test.tfvars` で使う。
workspace と `env` が合っていないと plan の前に止まる。作り方・向き先の切り替えは [docs/test_environment.md](../docs/test_environment.md)。

## state の置き場

state は S3（`ct125-logger-tfstate-<アカウントID>` の `infra/terraform.tfstate`、ap-northeast-1）に置き、S3 だけでロックする（`versions.tf` の `backend "s3"`）。test の state は同じバケットの `env:/test/infra/terraform.tfstate`。
`<アカウントID>` は `aws sts get-caller-identity --profile ct125-logger` で確かめる。どの PC でも `terraform init` すれば同じ state を使う。バケットは Terraform の外で作った（非公開・SSE-S3・HTTPS のみ・バージョニング）。
別の PC での準備は [docs/setup_another_pc.md](../docs/setup_another_pc.md)。

## 作るもの

| ファイル | リソース | 内容 |
|---|---|---|
| `environment.tf` | （リソースは無い） | 環境の名前 `env` と、そこから作る名前（本番は今のまま、test は `ct125-test-…`） |
| `s3.tf` | S3 バケット `ct125-logger-<アカウントID>` | 画面（React のビルド結果 `webapp/`）。非公開・SSE-S3・HTTPS のみ・バージョニング。CloudFront には `webapp/` だけ読ませる。作り直しの前の走行データ（`raw/` など）も残っている |
| `buckets.tf` | S3 バケット `ct125-logger-{raw,work,public}-<アカウントID>` | 生データ・作業用（処理の結果と記録・モデル・台帳）・公開用（画面が読む `datasets/shared/`）。設定は同じ（docs/data_flow_design.md 3.） |
| `local_pipeline.tf` | IAM ロール `ct125-local-pipeline` | PC の処理（`python -m ct125 process` など）が使う。生データを読み、作業用に書ける。公開用には書けない |
| `certificate.tf` | ACM 証明書（**us-east-1**） | `drive.herdio-system.com`。CloudFront 用なので us-east-1 に置く決まり |
| `cognito.tf` | Cognito ユーザープール・アプリクライアント・ログイン画面 | 新規登録は不可。認可コード＋PKCE |
| `cognito_users.tf` | ログインできるユーザー | `terraform.tfvars` の `app_users` と `app_user_passwords` どおりに作る |
| `data_api.tf` | API Gateway（HTTP API）・Lambda・IAM ロール・ログ | `/api/health` 以外は JWT が必要。Lambda は公開用のバケットの `datasets/*` だけ読める |
| `cloudfront.tf` | CloudFront・OAC | `/*` → S3 `webapp/`、`/api/*` → API Gateway |
| `ride_pipeline.tf` | ECR・Lambda（コンテナ）・IAM ロール・S3 イベント | 生データのバケットの `<走行>/upload_complete.json` で処理して公開。手動で `{"action":"retrain"}`・`{"action":"publish"}`。公開用に書けるのはこの Lambda だけ |
| `device_api.tf` | Lambda（デバイス API）・IAM ロール・API Gateway の POST ルート | ESP32 が生データを生データのバケットに直接置くための受付。権限は生データのバケットに置くことと機器トークンのハッシュを読むことだけ |

## 前提

- AWS CLI のプロファイル `ct125-logger`（鍵はこのフォルダーに置かない）
- リージョンは「新しい AWS 体験」のプロジェクトで固定（`ap-northeast-1`）。AWS Settings > View all projects > Overview > Additional Info > Region で確認
- `terraform.tfvars`（コミットしない）：`example.tfvars` をコピーして、ユーザー名とパスワードを書く
- データ API の zip：`api/scripts/build-lambda.ps1` で `api/dist/lambda.zip` を作っておく
- 走行データ処理のコンテナ：初回は ECR を先に作ってからイメージを上げる
  1. `terraform apply -target=aws_ecr_repository.pipeline`
  2. `pipeline/scripts/build-pipeline-image.ps1`（`pipeline_image.auto.tfvars` に digest を書く。書き換わったらコミットする）
  3. `terraform apply`
- 自宅周辺のマスクはやめた（#13）。処理の Lambda の SSM を読む権限は外した。SSM の `/ct125/private-points` は使っていない
- 役割ごとのバケットと 1 本の処理の流れの設計：[docs/data_flow_design.md](../docs/data_flow_design.md)
- PC の処理のロールを使うプロファイル（`~/.aws/config`）：`[profile ct125-local-pipeline]` に `role_arn = <terraform output -raw local_pipeline_role_arn>`・`source_profile = ct125-logger`・`region = ap-northeast-1`
- モデルの版：作業用のバケットの `models/current.json`（`{"version": "..."}`）。Lambda の retrain・publish が書き換える
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

apply の後、画面を出すのは `web/scripts/deploy.ps1`（Terraform の出力からログイン設定を作り、ビルドして S3 に上げる）。

## destroy して作り直すとき

- ユーザー・パスワードは `terraform.tfvars` から自動で戻る。ユーザープール ID とクライアント ID は変わるが、`deploy.ps1` が毎回 Terraform の出力から読むので、デプロイし直せば画面も追従する
- CloudFront のドメイン（`xxxx.cloudfront.net`）は変わるので、Cloudflare の `drive` の CNAME を直す
- S3 バケットは中身があると消えない（`force_destroy = false`）。生データを誤って消さないための意図的な設定。アプリ部分だけ消すなら `-target` で指定する

## 注意

- state にはユーザーのパスワードとアカウント ID が入る。S3 のバケットを公開しない・コミットしない
- パスワードの決まりは緩めてある（8 文字以上・英小文字と数字。`cognito.tf` の `password_policy`）。利用者が覚えやすいパスワードを使うため
