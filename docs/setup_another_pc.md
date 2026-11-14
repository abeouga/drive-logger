# 別の PC で開発を始める

リポジトリをクローンして、下の「秘密の情報」を手で置けば、どの PC からでも同じように開発・デプロイできます。
Terraform の state は S3 にあるので、PC ごとに持つ必要はありません。

## 1. ツールを入れる

| ツール | 使うところ | 備考 |
|---|---|---|
| Git・GitHub CLI（`gh`） | 全部 | リポジトリが非公開のときは、`gh auth login` でログインしてから clone |
| AWS CLI v2 | 全部 | 管理者のプロファイルの名前は自由（例：`ct125-logger`）。決めた名前を `infra/terraform.tfvars` の `aws_profile`・`infra/backend.hcl`・`pipeline/config/local.yaml` に書く（スクリプトは Terraform の出力の `aws_profile` から読む） |
| uv | `api/`・`pipeline/` | Python も uv が入れる（api は 3.13、pipeline は 3.12） |
| Node.js（LTS） | `web/` | |
| Terraform 1.10 以上 | `infra/` | S3 だけでロックする機能（`use_lockfile`）に 1.10 以上が要る |
| Docker | `pipeline/` のコンテナ | 自動処理の Lambda を作り直すときだけ |
| Arduino IDE | `firmware/` | ESP32 に書き込むときだけ |

スクリプトは PowerShell（`.ps1`）です。Windows ならそのまま、Mac・Linux では PowerShell 7（`pwsh`）を入れてください。

## 2. クローンする

日本語やスペースを含まない場所に置きます（日本語のパスはツールによって文字化けする）。

```bash
gh repo clone abeouga/drive-logger
```

## 3. AWS にログインする

リージョンは AWS の project のリージョン（AWS Settings > View all projects > Overview > Additional Info > Region で確認）。下の例のプロファイル名は `ct125-logger`。

```bash
aws configure set region <project のリージョン> --profile ct125-logger
```

おすすめは `aws login`（短い期限の認証情報。PC に鍵を残さない）。

```bash
aws login --profile ct125-logger
```

アクセスキーを使う場合は、**PC ごとに別のキーを作る**（ほかの PC の `~/.aws/credentials` をコピーしない）。PC をなくしたら、そのキーだけを無効にできます。

```bash
aws sts get-caller-identity --profile ct125-logger
```

## 4. Git に入っていないファイルを置く

| ファイル | 中身 | 作り方 |
|---|---|---|
| `infra/terraform.tfvars` | 管理者のプロファイル・アカウント ID・リージョン・画面のドメインの親と、アプリのユーザーとパスワード（**秘密**） | `example.tfvars` をコピーし、**いま使っているパスワードと同じ値**を入れる。違う値を入れると apply でパスワードが変わる。値はパスワード管理ソフトなどで受け渡し、チャットや Git には書かない |
| `infra/backend.hcl` | state のバケット名（アカウント ID が入る）・リージョン・プロファイル | `infra/backend.hcl.example` をコピーして埋める |
| `pipeline/config/local.yaml` | 管理者と処理のロールの AWS のプロファイル（`profile`・`pipeline_profile`）、`upload-sd` の送り先（`upload.base_url`）、test の同じ値（`environments.test`）。バケット名を決まりと違うものにするときだけ、その名前 | `pipeline/config/local.example.yaml` をコピーして埋める |
| `web/.env.development.local`（test は `web/.env.testenv.local`） | 画面のログインの設定と `/api/*` の中継先（秘密ではないが、環境に依るのでコミットしない） | Terraform が読める PC では `web/scripts/start-dev.ps1`（`-Env test`）が出力から作る。読めない PC では `web/.env.example` を見本に手で作る |
| `api/dist/lambda.zip` | データ API・デバイス API の Lambda | `api/scripts/build-lambda.ps1` で作る（Terraform が読む） |
| `CLAUDE.md` | AI 向けの短い案内（開発用の文書のリポジトリを指す） | 開発用の文書のリポジトリ（abeouga/agorack-document、非公開）をクローンし、`drive-logger/` の案内のとおりに置く |
| `.claude/launch.json` | 手元の開発サーバーの起動の設定（画面の `npm run dev` など） | 開発用の文書のリポジトリ（abeouga/agorack-document、非公開）の `drive-logger/` から写す |

次のものは自動で作られるか、要りません。

- `web/.env.local`：`npm run dev:local` の中継先（`LOCAL_API_ORIGIN`）を既定の http://localhost:8000 から変えるときだけ。`web/.env.example` を見る
- `web/.env.production.local`：`web/scripts/deploy.ps1` が Terraform の出力から作る
- `infra/pipeline_image.auto.tfvars`：コミット済み（イメージの digest だけ。ECR の住所は Terraform が組み立てる）。コンテナを作り直すと `build-pipeline-image.ps1` が書き換えるので、それもコミットする
- 走行データ：S3 にだけある。手元にデータのフォルダーは無く、処理も画面も S3 とデータ API から読む
- Wi-Fi のパスワードと機器トークン：ESP32 の中にある。ESP32 にまた書き込むときだけ要る（`firmware/scripts/provision-device.ps1`）

## 5. 準備する

```bash
cd api && uv sync
```

```bash
cd pipeline && uv venv --python 3.12 && uv pip install -e ".[dev]"
```

```bash
cd web && npm ci
```

```bash
terraform -chdir=infra init -reconfigure -backend-config=backend.hcl
```

確かめ方：

```bash
terraform -chdir=infra plan
```

Lambda の zip を作り直したばかりだと、データ API とデバイス API の 2 つの Lambda に「更新」が出ます（zip の中のファイルの時刻が変わるため）。中身のコードが同じなら apply しても害はありません。それ以外の変更や「作り直し」が出たら、apply せずに理由を調べます。

## 6. 2 台を行き来するときの決まり

- 作業を始める前に `git pull --rebase`、区切りで `git push`
- Terraform の apply は S3 でロックされるので、2 台が同時に apply しても片方が待たされるだけ。ロックが残ったまま（PC が落ちたなど）のときは、表示された ID で `terraform -chdir=infra force-unlock <ID>`。ほかの PC で apply 中でないことを確かめてから
- `pipeline_image.auto.tfvars` や `.terraform.lock.hcl` が変わったらコミットする（ほかの PC が古いイメージに戻さないように）

## Terraform の state の置き場

- S3 バケット `ct125-logger-tfstate-<アカウントID>` の `infra/terraform.tfstate`（プロジェクトのリージョン。`infra/backend.hcl` に書く）
- 非公開・SSE-S3・HTTPS のみ・バージョニングあり。壊れたら前の版に戻せる
- このバケットは Terraform の外で AWS CLI から作った（state を置く場所を、その state 自身で管理することはできないため）。消さないこと
- state にはユーザーのパスワードが入る。バケットを公開しない・ほかの人に読ませない
