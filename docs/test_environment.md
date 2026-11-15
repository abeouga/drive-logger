# test の環境

本番とは別に、AWS に test の環境を置く（#26 の決定、docs/data_flow_design.md 14.、実装は #83）。
ローカルの処理（`process`・`retrain`・`publish`）や画面の `dev:local` を test に向ければ、つないだ動きを本番に書かずに確かめられる。

## 1. 作り

| | 本番（prod） | test |
|---|---|---|
| 置き場所 | 今の AWS のプロジェクト、選択済みリージョン（ap-northeast-1） | 同じプロジェクト、同じリージョン。名前で分ける |
| Terraform の workspace | `default` | `test` |
| tfstate | `infra/terraform.tfstate`（今のまま） | `env:/test/infra/terraform.tfstate`（同じ state のバケット） |
| tfvars | `terraform.tfvars` | `test.tfvars`（`test.example.tfvars` から作る）と `pipeline_image.test.tfvars` |
| バケット | `ct125-logger-{raw,work,public}-<アカウントID>`、画面 `ct125-logger-<アカウントID>` | `ct125-logger-test-{raw,work,public}-<アカウントID>`、画面 `ct125-logger-test-<アカウントID>` |
| Lambda・API・ECR・ロール | `ct125-ride-pipeline`・`ct125-data-api`・`ct125-device-api`・`ct125-local-pipeline` など | `ct125-test-ride-pipeline`・`ct125-test-data-api`・`ct125-test-device-api`・`ct125-test-local-pipeline` など |
| ログインの利用者 | `ct125-app-users` | `ct125-test-app-users`（別の利用者とパスワード） |
| 機器トークンの置き場所（SSM） | `/ct125/devices/` | `/ct125-test/devices/` |
| 画面のドメイン | `drive.<base_domain>`（`base_domain` は `terraform.tfvars`） | `drive-test.<base_domain>`（`test.tfvars` の `app_domain` で変えられる） |
| ログイン画面の URL の先頭 | `ct125-drive-login` | `ct125-drive-login-test` |

- 名前は `infra/environment.tf` の `locals` で、`env` から作る。本番（`env = "prod"`）は今の名前のままになる
- どのロールの権限も、自分の環境のバケット・Lambda・SSM の場所だけを指す。test のロールは本番のリソースに届かない
- workspace と `env` が合っていないと、plan の前に止まる（`versions.tf` の `data "aws_caller_identity"`）。test の workspace で `-var-file=test.tfvars` を忘れたときや、本番の workspace で test の tfvars を渡したときに、本番を作り直す案が出ないようにするため
- test の処理の Lambda のイメージは test の ECR に置く。本番のイメージを指していると plan で止まる（`ride_pipeline.tf`）。ECR は古いイメージを本番 5 個・test 2 個まで残す
- test のリソースには `Environment = test` のタグが付く（費用を環境ごとに見るため）。本番のタグは変えていない

## 2. 作る前に確かめること

1. 支出の上限とプラン：AWS Settings > Billing で、支出の上限があるか・いくらか、有料プランかを見る。上限を超えるとプロジェクトが止まり、本番も使えなくなる
2. プランは CLI でも見られる

```bash
aws freetier get-account-plan-state --profile ct125-logger --region us-east-1
```

3. リージョン：AWS Settings > View all projects > Overview > Additional Info > Region が ap-northeast-1 であること

test の費用の目安（ap-northeast-1、ふだんの使い方で月あたり）：

| もの | 目安 | 根拠 |
|---|---|---|
| ECR（処理のコンテナ） | 約 0.07 ドル | 1 個 約 0.37 GB × 2 個 × 0.10 ドル/GB |
| S3（生データ・処理の結果・画面） | 0.01 ドル未満〜約 0.01 ドル | 本番の生データを全部写しても約 0.1 GB（0.025 ドル/GB） |
| Lambda・API Gateway・CloudWatch Logs | ほぼ 0 | 呼び出しは確かめるときだけ。無料の枠（本番と共有）に収まる |
| CloudFront・ACM・Cognito（Essentials）・SSM | 0 | 無料の枠に収まる・証明書と標準のパラメーターは無料 |
| 合計 | 月 0.1 ドル前後 | 学習し直しを何十回も回すと Lambda の料金が出る（3 GB × 15 分で 1 回 約 0.04 ドル、無料の枠を超えた分） |

## 3. 作る手順

`terraform apply` は、作るものを plan で確かめてからする。コマンドはどれもリポジトリの直下で打つ。

1. `infra/test.example.tfvars` をコピーして `infra/test.tfvars` を作り、test の利用者とパスワードを書く（本番と同じパスワードにしない。コミットしない）
2. workspace の test を作る（2 回目からは `terraform -chdir=infra workspace select test`）

```bash
terraform -chdir=infra workspace new test
```

3. 先に ECR と証明書だけを作る

```bash
terraform -chdir=infra apply -target=aws_ecr_repository.pipeline -target=aws_ecr_lifecycle_policy.pipeline -target=aws_acm_certificate.app -var-file=test.tfvars -var-file=pipeline_image.test.tfvars
```

4. Cloudflare に、証明書の確認用の CNAME をプロキシなし（DNS のみ）で足す。値は次で見る

```bash
terraform -chdir=infra output certificate_validation_record
```

5. test の ECR に処理のコンテナを上げる（`infra/pipeline_image.test.tfvars` が書き換わるので、コミットする）

```powershell
pipeline/scripts/build-pipeline-image.ps1 -Env test
```

6. データ API の zip を作り（`api/scripts/build-lambda.ps1`。本番と同じ zip）、全体を作る

```bash
terraform -chdir=infra apply -var-file=test.tfvars -var-file=pipeline_image.test.tfvars
```

7. Cloudflare に `drive-test` の CNAME を、`terraform -chdir=infra output -raw cloudfront_domain` に向けて、プロキシなしで足す
8. 画面を test に出す

```powershell
web/scripts/deploy.ps1 -Env test
```

9. 終わったら本番の workspace に戻す（戻し忘れても、次の plan は workspace と env が合わずに止まる）

```bash
terraform -chdir=infra workspace select default
```

## 4. test にデータを入れる

test の生データのバケットは空で始まる。本番の生データを写し、test の Lambda で学習し直して公開する。本番は読むだけで、書かない。

1. 受け付けの印（`upload_complete.json`）を除いて写す。印が届くと走行ごとの処理が動くので、モデルができる前には置かない

```bash
aws s3 sync s3://ct125-logger-raw-<アカウントID>/ s3://ct125-logger-test-raw-<アカウントID>/ --exclude "*/upload_complete.json" --exclude "_uploads/*" --profile ct125-logger
```

2. test の Lambda で、全走行で学習し直す（モデルを作り、公開する）

```bash
aws lambda invoke --function-name ct125-test-ride-pipeline --payload "{\"action\": \"retrain\"}" --cli-binary-format raw-in-base64-out --profile ct125-logger retrain.json
```

3. 受け付けの印を写す。走行ごとの処理が動き、台帳に受け付けの時刻などが入る

```bash
aws s3 sync s3://ct125-logger-raw-<アカウントID>/ s3://ct125-logger-test-raw-<アカウントID>/ --exclude "*" --include "*/upload_complete.json" --profile ct125-logger
```

この後、test の画面（workspace の test の `terraform output app_url`）に test の利用者でログインすると、走行一覧が開ける。

## 5. test のロールが本番に届かないことを確かめる

IAM のポリシーのシミュレーターで確かめる（本番に書こうとはしない）。どれも `implicitDeny` になればよい。

```bash
aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::<アカウントID>:role/ct125-test-local-pipeline --action-names s3:PutObject s3:GetObject --resource-arns arn:aws:s3:::ct125-logger-work-<アカウントID>/ledger/rides.json arn:aws:s3:::ct125-logger-raw-<アカウントID>/x --profile ct125-logger --query "EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision]" --output table
```

```bash
aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::<アカウントID>:role/ct125-test-ride-pipeline-role --action-names s3:PutObject --resource-arns arn:aws:s3:::ct125-logger-public-<アカウントID>/datasets/shared/x arn:aws:s3:::ct125-logger-work-<アカウントID>/x --profile ct125-logger --query "EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision]" --output table
```

```bash
aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::<アカウントID>:role/ct125-test-data-api-role --action-names s3:PutObject lambda:InvokeFunction --resource-arns arn:aws:s3:::ct125-logger-work-<アカウントID>/ledger/rides.json arn:aws:lambda:ap-northeast-1:<アカウントID>:function:ct125-ride-pipeline --profile ct125-logger --query "EvaluationResults[].[EvalActionName,EvalResourceName,EvalDecision]" --output table
```

同じコマンドで、test のバケット（`ct125-logger-test-…`）を指すと `allowed` になる。

## 6. ローカルの処理を test に向ける

1. `~/.aws/config` に test のロールのプロファイルを足す（`role_arn` は workspace の test で `terraform -chdir=infra output -raw local_pipeline_role_arn`）

```ini
[profile ct125-test-local-pipeline]
role_arn = arn:aws:iam::<アカウントID>:role/ct125-test-local-pipeline
source_profile = ct125-logger
region = ap-northeast-1
```

2. 命令ごとに `--env test` を付ける。画面 1 つの間ずっと test にするなら環境変数 `CT125_ENV`、PC の既定にするなら `config/local.yaml` の `aws.env`

```powershell
.venv/Scripts/python.exe -m ct125 --env test process --ride <走行 ID>
```

```powershell
$env:CT125_ENV = "test"
```

- どの命令も、最初に「向き先：test」のように向き先を出す
- test のときは、`config/local.yaml` の `aws`・`upload`（本番用に書いた値）は使わない。test だけの値は `config/local.yaml` の `environments.test` に書く
- 名前の決まりで決まる値（バケット名・Lambda・SSM の場所）は `config/default.yaml` の `environments.test`。PC に依る値（プロファイル・送り先のドメイン）は `config/local.yaml` の `environments.test`（見本は `config/local.example.yaml`）
- PC から SD の走行を test に送るときは、先に test の機器トークンを作る：`python -m ct125 --env test register-device --id pc01 --token-file config/pc01.test.token`

## 7. 画面を test に向ける

| 起動 | 向き先 |
|---|---|
| `start.bat -Env test`（`web/scripts/start-dev.ps1 -Env test`） | `/api/*` は test の画面のドメイン、ログインは test の Cognito。どちらの設定も Terraform（workspace の test）の出力から `web/.env.testenv.local`（コミットしない）に作る |
| `api/scripts/run-local.ps1 -Env test` と `npm run dev:local` | 手元のデータ API が、test のバケットと Lambda を使う（ログインなし、admin） |

- `npm run dev:test` は `web/.env.testenv.local`（中継先とログインの設定）を読む
- `api/scripts/run-local.ps1` は `-Env` を省くと本番を使う（今までの `web/docs/local_dev.md` の手順と同じ）

## 8. 消すとき

バケットは中身があると消えない（`force_destroy = false`）。test のバケットを空にしてから、workspace の test で `terraform -chdir=infra destroy -var-file=test.tfvars -var-file=pipeline_image.test.tfvars` を流す。Cloudflare の `drive-test` と証明書の確認用の CNAME も消す。
