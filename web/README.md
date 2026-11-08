# web：走行データの画面（React＋Vite）

ハンターカブ CT125 の走行データ（GPS＋振動）を、地図とタイムラインで見る画面です。

- 公開先：**https://drive.herdio-system.com/**（ログインが必要。ユーザーは `infra` の `terraform.tfvars` で管理）
- データを作る側は `pipeline/`。生データが S3 の `raw/` に届くと、AWS の Lambda（`ct125-ride-pipeline`）が前処理・点数付けをして `app/v1/datasets/shared/` に書き出す
- ログインした人にだけデータを返すデータ API は `api/`（FastAPI）。AWS のリソースは `infra/` の Terraform
- 表現上の制約（「故障予測」と言わない等）と「ECU / K-Line に触れない」は `docs/DEV_PLAN.md` 4. のとおり

手順は [docs/local_dev.md](docs/local_dev.md)、データの形は [docs/data_contract.md](docs/data_contract.md)。

---

## 全体の構成（公開版）

```
ブラウザ ─https→ CloudFront（drive.herdio-system.com）
                   ├─ /*      → S3 webapp/            React のビルド結果。走行データは入っていない
                   └─ /api/*  → API Gateway（JWT を検証）→ Lambda（api/、FastAPI）→ S3 app/v1/datasets/<データセット>/
ログイン：Cognito（managed login、認可コード＋PKCE）。アクセストークンを /api に付ける
```

- バケットは非公開のまま。CloudFront は `webapp/` だけ、Lambda は `app/v1/datasets/` だけを読める
- ユーザーごとにデータを分ける入口は `api/src/ct125_api/services/dataset_resolver.py`。今は全員が `shared` を見る

---

## 起動のしかたと、データの取り方（2 つ）

| 起動 | 使う場面 | データの取り方 | ログイン |
|---|---|---|---|
| `npm run dev` | ふだんの開発 | ブラウザ → Vite の dev サーバー（`/data/…`）→ ローカルの AWS プロファイルで S3 から取る（`cache/` にも保存） | なし |
| `npm run build`（`scripts/deploy.ps1`） | 公開版 | ブラウザ → CloudFront → データ API（`/api/data/…`） | **要** |

切り替えは `src/lib/dataSource.ts` の 1 か所（どれになるかは `vite.config.ts` が起動のしかたから決める）。
画面のコードは、どちらの場合も同じ `loadRides()`・`loadRide()` などを呼ぶだけ。

---

## ディレクトリ構成

```
web\
├── README.md  package.json  vite.config.ts  tsconfig.json  index.html
├── .env.example           ローカル開発の設定の見本（コミットする）
├── .env.local             実際の値（コミットしない）
├── .env.production.local  公開版のログイン設定。deploy.ps1 が Terraform の出力から作る（コミットしない）
├── start.bat              ダブルクリックで npm run dev
│
├── src/                   ブラウザで動くコード（React）
│   ├── main.tsx  App.tsx  index.css
│   ├── pages/             RideList（一覧）・Ride（走行ページ）・About
│   ├── components/        MapView・Timeline・Spectrogram・DetailPanel・RideCard・LoginScreen など
│   └── lib/
│       ├── data.ts        何を読むか（走行一覧・1 走行・スペクトログラム・生波形）
│       ├── dataSource.ts  どこから読むか（dev / hosted の切り替え）
│       ├── auth/          ログイン（authConfig・authClient・AuthGate）。公開版だけで働く
│       ├── types.ts       データの型（docs/data_contract.md と同じ形）
│       └── colors.ts  format.ts  route.ts  など
│
├── server/                Vite の dev サーバー（Node）の中だけで動くコード。ブラウザには出ない
│   └── s3-data.ts         /data/<ファイル名> → S3 の app/v1/datasets/shared/<ファイル名>。cache/ にも保存
│
├── scripts/
│   ├── start-dev.ps1      start.bat の中身
│   ├── deploy.ps1         公開：ログイン設定を作る → build → S3 webapp/ → CloudFront のキャッシュ削除
│   └── pull-data.ps1      S3 のデータを cache/ に丸ごと落とす（オフラインで触るとき）
│
├── cache/                 S3 から取ったデータの写し（コミットしない）
├── dist/                  ビルド結果（コミットしない）
└── docs/
    ├── local_dev.md       ローカルで動かす手順・困ったとき
    └── data_contract.md   画面用 JSON の形（pipeline の export と合わせる）
```

### S3 側の置き場所

```
s3://ct125-logger-<アカウントID>/          （非公開のまま。リージョンは ap-northeast-1）
├── raw/  processed/  models/            pipeline が使う（公開しない）
├── app/v1/datasets/shared/               この画面が読むデータ（全ユーザー共通）
│   ├── rides.json                        走行一覧
│   ├── ride_<id>.json                    1 秒窓の列（GPS なしの窓は lat/lon が null）
│   ├── spec_<id>.png ／ spec_<id>.json   スペクトログラム
│   └── wave_<id>.json                    見どころの生波形
└── webapp/                               React のビルド結果（CloudFront だけが読める）
```

`v1` はデータの形の版。形を変えるときは `v2/` を作り、古い画面が壊れないようにする。
置き場所は役割ごとのバケットに分ける予定（`docs/data_flow_design.md`）。

---

## ローカル開発の設定（`.env.local`）

`.env.example` をコピーして値を入れる。

| 変数 | 例 | 意味 |
|---|---|---|
| `DATA_SOURCE` | `s3` | `s3` か `cache` |
| `AWS_PROFILE` | `ct125-logger` | `~/.aws` のプロファイル |
| `AWS_REGION` | `ap-northeast-1` | バケットのリージョン |
| `S3_BUCKET` | `ct125-logger-<アカウントID>` | バケット名 |
| `S3_PREFIX` | `app/v1/datasets/shared/` | データの置き場所 |

**注意：`VITE_` で始まる変数はブラウザに埋め込まれる。** AWS の認証に関わる変数には `VITE_` を付けない。
（`.env.production.local` の `VITE_AUTH_*` はログイン画面の場所とクライアント ID で、ブラウザに見えてよい値）

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

http://localhost:5173 を開く。ログインはない。

- dev サーバーは **localhost だけで待ち受ける**（`--host` を付けない）。付けると同じ Wi-Fi の端末から S3 の中身が見えてしまう
- データを新しくしたいとき：機器から走行を送る（AWS が処理して S3 に書き出す）→ ブラウザを再読み込み

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
