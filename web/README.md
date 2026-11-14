# web：走行データの画面（React＋Vite）

ハンターカブ CT125 の走行データ（GPS＋振動）を、地図とタイムラインで見る画面です。

- 公開先：**https://drive.herdio-system.com/**（ログインが必要。ユーザーは `infra` の `terraform.tfvars` で管理）
- データを作る側は `pipeline/`。生データのバケットに走行が届くと、AWS の Lambda（`ct125-ride-pipeline`）が前処理・点数付けをして、公開用のバケットの `datasets/shared/` に書き出す
- ログインした人にだけデータを返すデータ API は `api/`（FastAPI）。AWS のリソースは `infra/` の Terraform
- 表現上の制約（「故障予測」と言わない等）と「ECU / K-Line に触れない」は [../docs/analysis_policy.md](../docs/analysis_policy.md) 1. のとおり

手順は [docs/local_dev.md](docs/local_dev.md)、データの形は [docs/data_contract.md](docs/data_contract.md)。

---

## 全体の構成（公開版）

```
ブラウザ ─https→ CloudFront（drive.herdio-system.com）
                   ├─ /*      → S3 webapp/            React のビルド結果。走行データは入っていない
                   └─ /api/*  → API Gateway（JWT を検証）→ Lambda（api/、FastAPI）→ 公開用のバケット datasets/<データセット>/
ログイン：アプリの画面からユーザープールに直接（USER_SRP_AUTH、更新は REFRESH_TOKEN_AUTH）。アクセストークンを /api に付ける
```

- バケットは非公開のまま。CloudFront は `webapp/` だけを読める。データ API の Lambda が読めるのは公開用のバケットの `datasets/` と作業用のバケットの台帳・処理の記録・モデルで、書けるのは台帳だけ（権限の全体は `infra/README.md` の `data_api.tf`）
- ユーザーごとにデータを分ける入口は `api/src/ct125_api/services/dataset_resolver.py`。今は全員が `shared` を見る

---

## 起動のしかたと、データの取り方

どの起動のしかたでも、画面はデータ API（`/api/*`）からだけ読む。S3 を直接読むコードは無い。

| 起動 | 使う場面 | `/api/*` の行き先 | ログイン |
|---|---|---|---|
| `npm run build`（`scripts/deploy.ps1`） | 公開版 | CloudFront → データ API | **要** |
| `npm run dev`（`start.bat`） | ふだんの開発 | Vite の dev サーバーが公開ドメインへ中継 | **要**（公開版と同じ） |
| `npm run dev:local` | API と画面を一緒に直すとき | 手元で動かしたデータ API（http://localhost:8000） | なし（手元の開発者＝admin） |
| `npm run dev:test`（`start.bat -Env test`） | 本番に書かずに、つないだ動きを確かめるとき | test の環境の公開ドメインへ中継 | **要**（test の Cognito。`../docs/test_environment.md`） |

API の呼び出しは `src/lib/dataSource.ts` の 1 か所。走行の一覧は `GET /api/rides`（走行の台帳）、1 走行のデータは `GET /api/data/<ファイル名>`。
admin でログインすると、走行を消す・ゴミ箱から戻す（#19）、前の処理の結果に戻す・モデルを切り替える（#20）ボタンが出る（最終的な判断はデータ API がする）。

---

## ディレクトリ構成

```
web/
├── README.md  package.json  vite.config.ts  tsconfig.json  index.html
├── .env.example                  dev の設定の見本（コミットする）
├── .env.development              dev のログイン設定（秘密ではない。Terraform が無い PC でも起動できるようにコミットする）
├── .env.development.local        dev のログイン設定。start-dev.ps1 が Terraform の出力から作る（コミットしない。.env.development より優先）
├── .env.production.local         公開版のログイン設定。deploy.ps1 が Terraform の出力から作る（コミットしない）
├── .env.testenv                  test の環境につなぐ dev サーバー（npm run dev:test）の中継先（秘密ではない。コミットする）
├── .env.testenv.local            test のログイン設定。start-dev.ps1 -Env test が Terraform（workspace の test）の出力から作る（コミットしない）
├── start.bat                     ダブルクリックで npm run dev
│
├── src/                   ブラウザで動くコード（React）
│   ├── main.tsx  App.tsx  index.css
│   ├── pages/             RideList（一覧）・Ride（走行ページ）・About・Trash（ゴミ箱。admin）
│   ├── components/        MapView・Timeline・Spectrogram・DetailPanel・RideCard・RunHistory（処理の記録）・ModelInfo（モデルの記録）など
│   └── lib/
│       ├── data.ts        何を読むか・書き換えるか（走行の一覧・1 走行・消す・戻す・処理の記録・モデル）
│       ├── dataSource.ts  データ API の呼び出し口（ログインのトークンを付ける）
│       ├── contract.check.ts  contracts/ の見本を型に当てる（型チェックだけ。ビルドには入らない）
│       ├── auth/          ログイン（authConfig・authClient・AuthGate）
│       ├── types.ts       データの型（contracts/app/・contracts/api/ と同じ形）
│       └── colors.ts  format.ts  route.ts  など
│
├── scripts/
│   ├── start-dev.ps1      start.bat の中身（ログインの設定を作ってから npm run dev）
│   ├── deploy.ps1         公開：ログイン設定を作る → build → S3 webapp/ → CloudFront のキャッシュ削除
│   ├── auth-env.ps1       ログインの設定のファイルを Terraform の出力から作る関数（start-dev.ps1 と deploy.ps1 が読み込む）
│   └── subset-brand-font.py  アプリの名前に使う字体から、名前の字だけの小さな woff2 を作る
│
├── dist/                  ビルド結果（コミットしない）
└── docs/
    ├── local_dev.md       ローカルで動かす手順・困ったとき
    └── data_contract.md   画面用 JSON の形（pipeline の export と合わせる）
```

### S3 側の置き場所

```
s3://ct125-logger-public-<アカウントID>/   公開用（非公開のまま。書けるのは処理の Lambda だけ）
└── datasets/shared/                      この画面が読むデータ（全ユーザー共通）
    ├── rides.json                        走行一覧
    ├── ride_<id>.json                    1 秒窓の列（GPS なしの窓は lat/lon が null）
    ├── spec_<id>.png ／ spec_<id>.json   スペクトログラム
    └── wave_<id>_<chunk>.json            1 秒窓の生波形（約 1 分ごと。1 秒を選んだときにその分だけ読む）
s3://ct125-logger-<アカウントID>/webapp/   React のビルド結果（CloudFront だけが読める）
```

生データ・作業用のバケットは `docs/data_flow_design.md`。データの形は `contracts/app/` に版付きで定義している。

---

## 設定

dev のログインの設定は、コミットしてある `.env.development` に入っている（ユーザープールとクライアント ID。秘密ではない）。Terraform が読める PC では `scripts/start-dev.ps1` が出力から `.env.development.local` も作り、こちらが優先される。`.env.development` が Terraform の出力と違っていると、`start-dev.ps1` と `deploy.ps1` が書き直して知らせるので、そのときはコミットする。

**注意：`VITE_` で始まる変数はブラウザに埋め込まれる。** `VITE_AUTH_*` はログイン画面の場所とクライアント ID で、ブラウザに見えてよい値。
画面には AWS の鍵もバケット名も入らない（データは必ずデータ API を通す）。

---

## 動かし方

### ローカル開発

ダブルクリックで起動するなら `start.bat`。手で起動するなら：

```bash
npm install
```

```bash
npm run dev
```

http://localhost:5173 を開き、公開版と同じユーザーでログインする。手順と、ログインなしで手元のデータ API につなぐ方法は [docs/local_dev.md](docs/local_dev.md)。

- データを新しくしたいとき：機器から走行を送る（AWS が処理して公開する）→ ブラウザを再読み込み

### 公開版を更新する

AWS のリソース（初回や、destroy した後）：

```bash
terraform -chdir=infra apply
```

データ API のコードを変えたら、zip を作り直してから上の apply：

```powershell
api\scripts\build-lambda.ps1
```

画面（React）を変えたら：

```powershell
web\scripts\deploy.ps1
```
