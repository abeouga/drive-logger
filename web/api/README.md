# ct125-api（データ API）

ログインした人にだけ、走行データ（S3 の `app/v1/datasets/<データセット>/`）を返す API です。
FastAPI で書き、AWS Lambda（Python 3.13・arm64）で動かします。

```
ブラウザ ─https→ CloudFront ─/api/*→ API Gateway（JWT を検証）→ Lambda（この API）→ S3
```

- **ログインの検証は API Gateway がする。** Cognito のアクセストークンの署名・期限・発行元を確かめ、
  通ったものだけを Lambda に渡す。この API は、API Gateway が渡す中身（claims）からユーザーを読むだけ
- **ユーザーごとにデータを分ける入口だけ作ってある。** 今は全員が `shared` を見る（`services/dataset_resolver.py`）

## エンドポイント

| パス | ログイン | 返すもの |
|---|---|---|
| `GET /api/health` | 不要 | `{"status": "ok"}` |
| `GET /api/me` | 要 | ユーザー名・グループ・見るデータセット |
| `GET /api/data/{file_name}` | 要 | データファイル（`rides.json`・`ride_<id>.json`・`spec_<id>.png` など。形は `../docs/data_contract.md`） |
| `GET /api/docs` | ― | 自動生成の説明書（OpenAPI） |

## フォルダー構成と役割

Java の MVC に近い形で、層ごとに分けています。上の層は下の層だけを使い、逆向きには使いません。

```
src/ct125_api/
├── main.py                 アプリの組み立て（ルーターと例外の対応を登録）
├── lambda_handler.py       Lambda の入口（Mangum で FastAPI につなぐ）
├── config.py               設定（環境変数から読む）
├── dependencies.py         部品の組み立て（Depends で注入する。テストで差し替える）
├── errors.py               業務上の失敗 → HTTP ステータスの対応表
│
├── routers/                ① HTTP の入口（Controller）。受け取ってサービスを呼ぶだけ
│   ├── health_router.py
│   ├── me_router.py
│   └── data_router.py
├── schemas/                ② 返す JSON の形（View / DTO）
│   └── responses.py
├── services/               ③ 業務の流れ（Service）
│   ├── data_file_service.py    ファイル名の検査 → データセットを決める → 読む
│   └── dataset_resolver.py     ユーザー → データセット（今は全員 shared）
├── repositories/           ④ データの置き場所とのやりとり（DAO / Repository）
│   ├── data_file_repository.py     約束（インターフェース）
│   └── s3_data_file_repository.py  S3 での実装
├── auth/
│   └── current_user.py     API Gateway が渡す claims → User
└── domain/                 ⑤ 業務の言葉と決まり（どの層からも使う。FastAPI にも AWS にも依存しない）
    ├── user.py  dataset.py  data_file.py
    └── exceptions.py
```

| 変えたいこと | 触るファイル |
|---|---|
| ユーザーごとにデータを分ける | `services/dataset_resolver.py` だけ |
| 新しいエンドポイントを足す | `routers/` に 1 ファイル、`main.py` に 1 行、返す形は `schemas/` |
| S3 以外から読む | `repositories/` に実装を足し、`dependencies.py` で差し替える |
| 返せるファイルの種類を増やす | `domain/data_file.py` の `MEDIA_TYPES` |

## ローカルで動かす

```bash
uv sync
```

```bash
uv run pytest
```

S3 の本物のデータで API を動かすとき（ログインなしで「ローカルの開発者」として扱う）：

```powershell
$env:AWS_PROFILE="ct125-logger"; $env:DATA_BUCKET="ct125-logger-<アカウントID>"; $env:ALLOW_LOCAL_USER="true"; uv run uvicorn ct125_api.main:app --reload --app-dir src
```

http://localhost:8000/api/docs で説明書が開きます。`ALLOW_LOCAL_USER` は Lambda では設定しません。

## Lambda 用の zip を作る

```powershell
./scripts/build-lambda.ps1
```

`dist/lambda.zip` ができます。Terraform（`D:\ct125-logger-terraform`）がこれを Lambda に上げます。
