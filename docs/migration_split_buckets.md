# 本番の移し替え：役割ごとのバケットと、1 本の処理の流れ（#6）

`docs/data_flow_design.md` 12. の手順を、コマンドまで書いたもの。**画面を止めずに**移す。どの段階でも前に戻せる（今のバケットの中身は消さない）。

> **2026-11-09 に、この手順で本番を移した**（結果は docs/PROGRESS.md）。前の状態の印は git のタグ `before-split-buckets`。

- 前提：AWS のプロファイル `ct125-logger` でログイン済み。リージョンは ap-northeast-1（AWS Settings > View all projects > Overview > Additional Info > Region で確認）
- Docker Desktop が起動している（新しい処理のコンテナを作る）
- PowerShell で、リポジトリのルートから流す
- 所要：30 分ほど。費用：S3 のバケット 3 つ（中身は合わせて約 100 MB）と、学習し直し 1 回分の Lambda。月に数円の見込み

## 0. 前の状態に印を付ける

```powershell
git tag before-split-buckets origin/main
```

（移し替えの PR をマージする前の main に印を付ける。戻すときに使う）

```powershell
terraform -chdir=infra plan
```

差分が「追加 25・変更 6・置き換え 2（S3 のイベントと Lambda の呼び出し権限が、生データのバケットに移る）」であることを確かめる。今のバケットと中身は消えない。

## 1. 新しいバケットとローカルの処理のロールだけを作る（足すだけ）

```powershell
terraform -chdir=infra apply -target='aws_s3_bucket.role' -target='aws_s3_bucket_ownership_controls.role' -target='aws_s3_bucket_public_access_block.role' -target='aws_s3_bucket_server_side_encryption_configuration.role' -target='aws_s3_bucket_versioning.role' -target='aws_s3_bucket_lifecycle_configuration.role' -target='aws_s3_bucket_policy.role' -target='aws_iam_role.local_pipeline' -target='aws_iam_role_policy.local_pipeline'
```

```powershell
terraform -chdir=infra output -raw work_bucket_name
```

（出なければ `terraform -chdir=infra apply -refresh-only` で出力を作り直す）

## 2. 今のデータを新しいバケットに写す（今のバケットの中身は消さない）

生データ（`raw/<走行>/` → 生データのバケットの直下 `<走行>/`）。S3 のイベントはまだ新しいバケットに付いていないので、写しても処理は動かない：

```powershell
$raw = terraform -chdir=infra output -raw raw_bucket_name
aws s3 sync s3://ct125-logger-535562976288/raw/ "s3://$raw/" --profile ct125-logger
```

モデル（`models/` → 作業用のバケットの `models/`。学習し直しの前に、新しい走行が来ても処理できるように）：

```powershell
$work = terraform -chdir=infra output -raw work_bucket_name
aws s3 sync s3://ct125-logger-535562976288/models/ "s3://$work/models/" --profile ct125-logger
```

```powershell
aws s3 ls "s3://$raw/" --profile ct125-logger
```

（ride_001〜ride_009 の 9 個が出ること）

## 3. 新しい処理のコンテナを作って ECR に上げる

```powershell
pipeline\scripts\build-pipeline-image.ps1
```

`infra/pipeline_image.auto.tfvars` の digest が書き換わる（後でコミットする）。前のイメージは ECR に残る（5 個まで）。

## 4. 処理の Lambda だけを新しい流れに切り替える

画面（データ API）は、まだ今のバケットを読むので、表示は変わらない。

```powershell
terraform -chdir=infra apply -target='aws_lambda_function.pipeline' -target='aws_iam_role_policy.pipeline' -target='aws_lambda_permission.s3_invoke_pipeline' -target='aws_s3_bucket_notification.raw_upload_complete'
```

## 5. 学習し直して、公開用を作る

分類どおり（停車・実走だけ）に学習し、全走行を点数付けし直し、公開用のバケットに書き出す。

```powershell
aws lambda invoke --function-name ct125-ride-pipeline --cli-binary-format raw-in-base64-out --payload '{\"action\":\"retrain\"}' --cli-read-timeout 900 --profile ct125-logger retrain.json
Get-Content retrain.json
```

確かめること：

- `status` が `succeeded`、走行の分類が ride_006＝desk、ride_001〜003＝idle、ride_004・005＝ride、ride_007〜009＝ride_nogps
- 公開用のバケットに 8 走行（ride_006 は机上なので出さない）

```powershell
$public = terraform -chdir=infra output -raw public_bucket_name
aws s3 ls "s3://$public/datasets/shared/" --profile ct125-logger
```

```powershell
aws s3 cp "s3://$work/ledger/rides.json" - --profile ct125-logger
```

## 6. データ API とデバイス API を新しいバケットに向ける

```powershell
terraform -chdir=infra apply
```

ここで画面が公開用のバケットを読み始め、機器からの送信も生データのバケットに入るようになる。

## 7. 画面で確かめる

- https://drive.herdio-system.com/ にログインし、一覧が 8 走行（ride_006 が無い）で、走行ページの地図・グラフ・スペクトログラムが出る
- 自宅周辺の窓にも座標が入っている（マスクをやめたので）

## 8. 手元の設定を直す

画面の dev サーバー（`web/.env.local`）：

```
S3_BUCKET=ct125-logger-public-<アカウントID>
S3_PREFIX=datasets/shared/
```

ローカルの処理のロール（`~/.aws/config` に足す）：

```
[profile ct125-local-pipeline]
role_arn = <terraform output -raw local_pipeline_role_arn>
source_profile = ct125-logger
region = ap-northeast-1
```

`pipeline/config/local.yaml` に `aws: {pipeline_profile: ct125-local-pipeline}`。確かめる：

```powershell
cd pipeline; .venv\Scripts\python.exe -m ct125 rides
```

## 9. コミットする

`infra/pipeline_image.auto.tfvars`（新しい digest）をコミットする。

## 戻すとき

今のバケットの中身（`raw/`・`processed/`・`models/`・`app/v1/datasets/shared/`）は消していないので、設定を戻せば前のとおりに動く。

```powershell
git checkout before-split-buckets -- infra pipeline/deploy pipeline/src
terraform -chdir=infra apply
```

（新しいバケットは残る。要らなければ、中身を確かめてから消す）

## 後でやること（本人の了承の後）

- 9 走行をデバイス API から上げ直し、新しい名前（`ride_<日時>`）にそろえる（#15。#14 の道具を使う）
- 今のバケットの古い場所（`raw/`・`processed/`・`models/`・`app/`・`site/`）を消す（消すと戻せなくなるので、新しい流れで数日動いてから）
- SSM の `/ct125/private-points`（自宅のマスクをやめたので使わない）を消す
