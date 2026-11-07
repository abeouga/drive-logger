# ct125-api（データ API とデバイス API）

FastAPI で書き、AWS Lambda（Python 3.13・arm64）で動かします。同じコードから **2 つの Lambda** を作ります。

| アプリ | Lambda | 使う人 | できること | 認証 |
|---|---|---|---|---|
| データ API（`main.py`） | `ct125-data-api` | ブラウザ（ログインした人） | 走行データ（S3 の `app/v1/datasets/<データセット>/`）を**読む**だけ | Cognito の JWT（API Gateway が検証） |
| デバイス API（`device_main.py`） | `ct125-device-api` | ESP32（機器） | 生データを S3 の `raw/<走行>/` に**置く**だけ（署名付き URL を出す） | 機器トークン（このアプリが検証） |

権限を分けるために、アプリも Lambda も分けています（画面用は raw/ に書けない、機器用は公開データを読めない）。

```
ブラウザ ─https→ CloudFront ─/api/*→ API Gateway ─GET（JWT 検証済み）→ データ API ─→ S3 app/v1/datasets/
ESP32    ─https→ CloudFront ─/api/device/*→ API Gateway ─POST→ デバイス API ─→ 署名付き URL
ESP32    ─https（署名付き URL）→ S3 raw/<走行>/ → 完了の合図 → 自動処理（ct125-ride-pipeline）
```

- **ログインの検証は API Gateway がする。** Cognito のアクセストークンの署名・期限・発行元を確かめ、
  通ったものだけを Lambda に渡す。データ API は、API Gateway が渡す中身（claims）からユーザーを読むだけ
- **ユーザーごとにデータを分ける入口だけ作ってある。** 今は全員が `shared` を見る（`services/dataset_resolver.py`）
- **機器は AWS の鍵を持たない。** 持つのは取り消せる機器トークンだけ。トークンでできるのは「raw/ に新しい走行を置く」ことだけ

## エンドポイント

| パス | 認証 | 返すもの |
|---|---|---|
| `GET /api/health` | 不要 | `{"status": "ok"}` |
| `GET /api/me` | ログイン | ユーザー名・グループ・見るデータセット |
| `GET /api/data/{file_name}` | ログイン | データファイル（`rides.json`・`ride_<id>.json`・`spec_<id>.png` など。形は `../docs/data_contract.md`） |
| `GET /api/docs` | ― | データ API の説明書（OpenAPI） |
| `POST /api/device/uploads` | 機器 | 送るファイルと大きさ → 走行名（`ride_<日時>`）とファイルごとの PUT 用 URL（15 分）。途中で切れたら前回の走行名を付けて呼び直す |
| `POST /api/device/uploads/{ride_id}/complete` | 機器 | S3 の大きさが申告どおりなら完了の合図を置く（違えば 409）。完了済みなら `already_complete` |

機器の認証ヘッダー：`Authorization: Device <機器ID>.<トークン>`。機器の登録・無効化は ct125-logger の
`python -m ct125 register-device --id d01` / `revoke-device`。手順のお手本は ct125-logger の `tools/device_upload_simulator.py`。

## フォルダー構成と役割

Java の MVC に近い形で、層ごとに分けています。上の層は下の層だけを使い、逆向きには使いません。

```
src/ct125_api/
├── main.py                   データ API の組み立て
├── device_main.py            デバイス API の組み立て
├── lambda_handler.py         データ API の Lambda の入口（Mangum）
├── device_lambda_handler.py  デバイス API の Lambda の入口
├── config.py                 設定（環境変数から読む。Settings と DeviceSettings）
├── dependencies.py           データ API の部品の組み立て（Depends で注入する。テストで差し替える）
├── device_dependencies.py    デバイス API の部品の組み立て
├── errors.py                 業務上の失敗 → HTTP ステータスの対応表（両方のアプリで使う）
│
├── routers/                  ① HTTP の入口（Controller）。受け取ってサービスを呼ぶだけ
│   ├── health_router.py  me_router.py  data_router.py
│   └── device_upload_router.py
├── schemas/                  ② やりとりする JSON の形（View / DTO）
│   ├── responses.py
│   └── device_upload.py      ESP32 のファームウェアとの約束
├── services/                 ③ 業務の流れ（Service）
│   ├── data_file_service.py      ファイル名の検査 → データセットを決める → 読む
│   ├── dataset_resolver.py       ユーザー → データセット（今は全員 shared）
│   ├── device_authenticator.py   機器トークンのハッシュを照合する
│   └── raw_upload_service.py     受け付け → URL を出す → 大きさを確かめて完了
├── repositories/             ④ データの置き場所とのやりとり（DAO / Repository）。約束と実装を分けてある
│   ├── data_file_repository.py      ／ s3_data_file_repository.py
│   ├── device_token_repository.py   ／ ssm_device_token_repository.py
│   └── raw_upload_repository.py     ／ s3_raw_upload_repository.py
├── auth/
│   └── current_user.py       API Gateway が渡す claims → User
└── domain/                   ⑤ 業務の言葉と決まり（FastAPI にも AWS にも依存しない）
    ├── user.py  dataset.py  data_file.py
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
$env:AWS_PROFILE="ct125-logger"; $env:DATA_BUCKET="ct125-logger-<アカウントID>"; $env:ALLOW_LOCAL_USER="true"; uv run uvicorn ct125_api.main:app --reload --app-dir src
```

http://localhost:8000/api/docs で説明書が開きます。`ALLOW_LOCAL_USER` は Lambda では設定しません。

## Lambda 用の zip を作る

```powershell
./scripts/build-lambda.ps1
```

`dist/lambda.zip` ができます。Terraform（`infra`）がこれを 2 つの Lambda に上げます（ハンドラーだけが違う）。
