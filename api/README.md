# ct125-api（データ API とデバイス API）

FastAPI で書き、AWS Lambda（Python 3.13・arm64）で動かします。同じコードから **2 つの Lambda** を作ります。

| アプリ | Lambda | 使う人 | できること | 認証 |
|---|---|---|---|---|
| データ API（`main.py`） | `ct125-data-api` | ブラウザ（ログインした人） | 走行データ（公開用のバケットの `datasets/<データセット>/`）を**読む**だけ | Cognito の JWT（API Gateway が検証） |
| デバイス API（`device_main.py`） | `ct125-device-api` | ESP32（機器） | 生データを生データのバケットの `<走行>/` に**置く**だけ（署名付き URL を出す） | 機器トークン（このアプリが検証） |

権限を分けるために、アプリも Lambda も分けています（画面用は生データに書けない、機器用は公開データを読めない）。

```
ブラウザ ─https→ CloudFront ─/api/*→ API Gateway ─GET（JWT 検証済み）→ データ API ─→ S3 公開用 datasets/
ESP32    ─https→ CloudFront ─/api/device/*→ API Gateway ─POST→ デバイス API ─→ 署名付き URL
ESP32    ─https（署名付き URL）→ S3 生データ <走行>/ → 完了の合図 → 自動処理（ct125-ride-pipeline）
```

- **ログインの検証は API Gateway がする。** Cognito のアクセストークンの署名・期限・発行元を確かめ、
  通ったものだけを Lambda に渡す。データ API は、API Gateway が渡す中身（claims）からユーザーを読むだけ
- **ユーザーごとにデータを分ける入口だけ作ってある。** 今は全員が `shared` を見る（`services/dataset_resolver.py`）
- **機器は AWS の鍵を持たない。** 持つのは取り消せる機器トークンだけ。トークンでできるのは「生データのバケットに新しい走行を置く」ことだけ

## エンドポイント

| パス | 認証 | 返すもの |
|---|---|---|
| `GET /api/health` | 不要 | `{"status": "ok"}` |
| `GET /api/me` | ログイン | ユーザー名・グループ・見るデータセット |
| `GET /api/data/{file_name}` | ログイン | データファイル（`rides.json`・`ride_<id>.json`・`spec_<id>.png` など。形は `../web/docs/data_contract.md`） |
| `GET /api/rides` | ログイン | 走行の台帳から作った一覧（画面に出す走行と要約）。admin は `?include_deleted=true` で消した走行も |
| `DELETE /api/rides/{ride_id}` | admin | 走行を画面と学習から外す（生データは残す）。処理の Lambda に公開用の作り直しを頼む |
| `POST /api/rides/{ride_id}/restore` | admin | 外した走行を戻す |
| `POST /api/rides/{ride_id}/purge` | admin | ゴミ箱の走行を完全に削除する（#82。元に戻せない）。本文の `confirm_ride_id` が走行 ID と同じでなければ 400、ゴミ箱に無ければ 409。台帳の 1 件を除いて公開し直しを頼み、処理の結果 → 生データの順に消す。誰がいつ消したかはデータ API のログに残る |
| `GET /api/rides/{ride_id}/runs` | ログイン | その走行を処理した記録（新しい順。どれを画面に出しているか） |
| `PUT /api/rides/{ride_id}/published-run` | admin | 画面に出す結果を、前の処理の結果などに切り替える |
| `GET /api/models` | ログイン | モデルの版の一覧と、今使っている版 |
| `GET /api/models/{version}`・`/notes` | ログイン | その版の記録（model.json）とナレッジ（notes.md） |
| `PUT /api/models/current` | admin | 今使うモデルを切り替える（全走行の点数付けし直しは処理の Lambda。202 を返し、数分で画面に出る） |
| `GET /api/docs` | ― | データ API の説明書（OpenAPI） |
| `POST /api/device/uploads` | 機器 | 送るファイルと大きさ → 走行名（`ride_<日時>`）とファイルごとの PUT 用 URL（15 分）。途中で切れたら前回の走行名を付けて呼び直す |
| `POST /api/device/uploads/{ride_id}/complete` | 機器 | S3 の大きさが申告どおりなら完了の合図を置く（違えば 409）。完了済みなら `already_complete` |

応答の形は `../contracts/api/`（`tests/test_rides_api.py` が定義に当てる）。データ API が書けるのは作業用のバケットの台帳（`ledger/rides.json`）だけで、公開用には書けない。
完全に削除のときだけ、生データの `<ride_id>/` 以下と、作業用の `runs/<run_id>/rides/<ride_id>/` 以下を消せる（読めない）。`run.json` とモデルは記録なので消さない。

機器の認証ヘッダー：`Authorization: Device <機器ID>.<トークン>`。機器の登録・無効化は pipeline の
`python -m ct125 register-device --id d01` / `revoke-device`。PC から送る道具は pipeline の `python -m ct125 upload-sd`（ESP32 と同じ手順）。
同じ SD の走行（セッション名と必須のファイルの大きさが同じ）を送り終えていれば、`POST /api/device/uploads` は既にある走行 ID を `status: already_uploaded`・`uploads: []` で返す（#14。印は生データのバケットの `_uploads/`）。

## フォルダー構成と役割

Java の MVC に近い形で、層ごとに分けています。上の層は下の層だけを使い、逆向きには使いません。

```
src/ct125_api/
├── main.py                   データ API の組み立て
├── device_main.py            デバイス API の組み立て
├── lambda_handler.py         データ API の Lambda の入口（Mangum）
├── device_lambda_handler.py  デバイス API の Lambda の入口
├── config.py                 設定（環境変数から読む。Settings と DeviceSettings。環境に依る値は既定を持たず、Terraform が渡す）
├── dependencies.py           データ API の部品の組み立て（Depends で注入する。テストで差し替える）
├── device_dependencies.py    デバイス API の部品の組み立て
├── errors.py                 業務上の失敗 → HTTP ステータスの対応表（両方のアプリで使う）
│
├── routers/                  ① HTTP の入口（Controller）。受け取ってサービスを呼ぶだけ
│   ├── health_router.py  me_router.py  data_router.py
│   ├── rides_router.py       走行の台帳・処理の記録・消す・戻す・完全に削除
│   ├── models_router.py      モデルの記録と切り替え
│   └── device_upload_router.py
├── schemas/                  ② やりとりする JSON の形（View / DTO）
│   ├── responses.py
│   └── device_upload.py      ESP32 のファームウェアとの約束
├── services/                 ③ 業務の流れ（Service）
│   ├── data_file_service.py      ファイル名の検査 → データセットを決める → 読む
│   ├── dataset_resolver.py       ユーザー → データセット（今は全員 shared）
│   ├── ride_service.py           台帳・処理の記録・モデルを見る／変える（変えるのは admin だけ）
│   ├── pipeline_client.py        処理の Lambda に公開の作り直し・モデルの切り替えを頼む（非同期）
│   ├── device_authenticator.py   機器トークンのハッシュを照合する
│   └── raw_upload_service.py     受け付け → URL を出す → 大きさを確かめて完了
├── repositories/             ④ データの置き場所とのやりとり（DAO / Repository）。約束と実装を分けてある
│   ├── data_file_repository.py      ／ s3_data_file_repository.py
│   ├── device_token_repository.py   ／ ssm_device_token_repository.py
│   ├── raw_upload_repository.py     ／ s3_raw_upload_repository.py
│   ├── work_repository.py           作業用のバケットを読む（台帳・処理の記録・モデル）。書けるのは台帳だけ
│   └── ride_files_repository.py     完全に削除のときに、走行の生データと処理の結果を消す
├── auth/
│   └── current_user.py       API Gateway が渡す claims → User
└── domain/                   ⑤ 業務の言葉と決まり（FastAPI にも AWS にも依存しない）
    ├── user.py  dataset.py  data_file.py
    ├── ledger.py             走行の台帳の書き換えの決まり（消す・戻す・完全に削除）
    ├── device.py             機器と、その認証情報の形
    ├── raw_upload.py         送れるファイル・大きさの上限・走行名の付け方・受け付けの記録
    └── exceptions.py
```

| 変えたいこと | 触るファイル |
|---|---|
| ユーザーごとにデータを分ける | `services/dataset_resolver.py` だけ |
| 新しいエンドポイントを足す | `routers/` に 1 ファイル、`main.py`（または `device_main.py`）に 1 行、形は `schemas/` |
| S3 以外から読む | `repositories/` に実装を足し、`dependencies.py` で差し替える |
| 機器から送れるファイル・上限を変える | `domain/raw_upload.py` |
| 返せるファイルの種類を増やす | `domain/data_file.py` の `MEDIA_TYPES` |

## ローカルで動かす

```bash
uv sync
```

```bash
uv run pytest
```

S3 の本物のデータでデータ API を動かすとき（ログインなしで「ローカルの開発者」として扱う）：

```powershell
$env:AWS_PROFILE="<管理者のプロファイル>"; $env:DATA_BUCKET="ct125-logger-public-<アカウントID>"; $env:WORK_BUCKET="ct125-logger-work-<アカウントID>"; $env:PIPELINE_FUNCTION="ct125-ride-pipeline"; $env:RAW_BUCKET="ct125-logger-raw-<アカウントID>"; $env:ALLOW_LOCAL_USER="true"; uv run uvicorn ct125_api.main:app --reload --port 8000 --app-dir src
```

http://localhost:8000/api/docs で説明書が開きます。`ALLOW_LOCAL_USER` は Lambda では設定しません。
管理者のプロファイルで動かすと、ゴミ箱の「完全に削除」は本番の生データを本当に消します（`RAW_BUCKET` はそのためだけに使う）。

## Lambda 用の zip を作る

```powershell
./scripts/build-lambda.ps1
```

`dist/lambda.zip` ができます。Terraform（`infra`）がこれを 2 つの Lambda に上げます（ハンドラーだけが違う）。
