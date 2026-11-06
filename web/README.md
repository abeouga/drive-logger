# ct125-app（CT125 走行データ Web アプリのフロント）

ハンターカブ CT125 の走行データ（GPS＋振動）を、地図とタイムラインで見る Web アプリのフロントです。
**Vite で動かし、データは S3 から取ってくる**ためのプロジェクトです。

- データを作る側（解析パイプライン、Python）は `D:\カブロガー\ct125-logger`。`python -m ct125 export` が JSON を作り、S3 の `app/v1/` に上げる
- このフォルダーはデータを**読むだけ**。S3 にもローカルの元データにも書き込まない
- 表現上の制約（「故障予測」と言わない等）と「ECU / K-Line に触れない」は ct125-logger の `docs/DEV_PLAN.md` 4. のとおり

> 状態（2026-11-06）：移行済み。dev（S3／cache）と 1 ファイルビルドが動く。画面は走行一覧・走行ページ（地図・タイムライン・スペクトログラム・詳細と生波形、スマホはタブ切り替え）・この分析について。S3 の `app/v1/` にデータを上げ、`DATA_SOURCE=s3` で読めることを確認済み（2026-11-06）。1 ファイルの `site-app/index.html` へのアップロードはまだ。手順は [docs/local_dev.md](docs/local_dev.md)、データの形は [docs/data_contract.md](docs/data_contract.md)。

---

## ディレクトリ構成

```
D:\ct125-app\
├── README.md              このファイル
├── package.json           vite / react / typescript / maplibre-gl / echarts / tailwindcss / vite-plugin-singlefile
│                          ＋ dev だけ @aws-sdk/client-s3・@aws-sdk/credential-providers
├── vite.config.ts         dev：/data/* を server/s3-data.ts に渡す／build：1 ファイル（singlefile）
├── tsconfig.json
├── index.html
├── .env.example           設定の見本（コミットする）
├── .env.local             実際の値（コミットしない）
├── .gitignore
│
├── src/                   ブラウザで動くコード（React）
│   ├── main.tsx  App.tsx  index.css
│   ├── pages/             RideList（一覧）・Ride（走行ページ）・About
│   ├── components/        MapView・Timeline・Spectrogram・DetailPanel・RideCard・Legend・Sparkline
│   └── lib/
│       ├── data.ts        データの取り方をここ 1 か所に集める（fetch("/data/…")）
│       ├── types.ts       データの型（docs/data_contract.md と同じ形）
│       └── colors.ts  format.ts  route.ts
│
├── server/                Vite の dev サーバー（Node）の中だけで動くコード。ブラウザには出ない
│   └── s3-data.ts         /data/<ファイル名> → S3 の app/v1/<ファイル名> を GetObject して返す。cache/ にも保存
│
├── scripts/
│   ├── pull-data.ps1      S3 の app/v1/ を cache/ に丸ごと落とす（オフラインで触るとき）
│   └── build-single.ps1   pull-data → npm run build（cache/ のデータを入れた 1 ファイルを dist/ に）
│
├── public/                そのまま配る静的ファイル（アイコン等。データは置かない）
├── cache/                 S3 から取ったデータの写し（コミットしない）
├── dist/                  ビルド結果 index.html 1 ファイル（コミットしない）
└── docs/
    ├── local_dev.md       ローカルで動かす手順・困ったとき
    └── data_contract.md   S3 の app/v1/ に置く JSON の形（ct125-logger の export と合わせる）
```

### S3 側の置き場所

```
s3://ct125-logger-<アカウントID>/          （非公開のまま。リージョンは ap-northeast-1）
├── raw/  processed/  models/  site/      既存（ct125-logger が使う）
├── app/v1/                               新規：このアプリが読むデータ
│   ├── rides.json                        走行一覧
│   ├── ride_<id>.json                    1 秒窓の列（自宅周辺は lat/lon が null）
│   ├── spec_<id>.png ／ spec_<id>.json   スペクトログラム（11/9 分）
│   └── wave_<id>.json                    見どころの生波形（11/9 分）
└── site-app/index.html                   ビルドした 1 ファイル（署名付き URL で配る）
```

`v1` はデータの形の版。形を変えるときは `v2/` を作り、古いアプリが壊れないようにする。

---

## データの流れ（3 つのモード）

| モード | 使う場面 | データの出どころ | 設定 |
|---|---|---|---|
| **s3**（既定） | ふだんの開発 | ブラウザ → Vite の dev サーバー（`/data/…`）→ **ローカルの AWS プロファイルで S3 から取得** → `cache/` にも保存 | `.env.local` の `DATA_SOURCE=s3` |
| **cache** | 回線がない・S3 を叩きたくない | `cache/` だけ | `DATA_SOURCE=cache` |
| **build** | 配布用の 1 ファイル | `cache/` の JSON をビルド時に HTML に埋め込む | `npm run build` |

ブラウザから S3 を直接読まず、dev サーバーを経由させる理由：

- **AWS の認証情報がブラウザに出ない**（dev サーバーの Node が `~/.aws` のプロファイルを使う）
- **バケットを非公開のまま**にでき、S3 の CORS 設定も要らない
- アプリ側のコードは本番（1 ファイル）と同じ `fetch("/data/…")` で書ける

---

## 設定（`.env.local`）

`.env.example` をコピーして値を入れる。

| 変数 | 例 | 意味 |
|---|---|---|
| `DATA_SOURCE` | `s3` | `s3` か `cache` |
| `AWS_PROFILE` | `ct125-logger` | `~/.aws` のプロファイル |
| `AWS_REGION` | `ap-northeast-1` | バケットのリージョン |
| `S3_BUCKET` | `ct125-logger-<アカウントID>` | バケット名 |
| `S3_PREFIX` | `app/v1/` | データの置き場所 |

**注意：`VITE_` で始まる変数はブラウザに埋め込まれる。** AWS 関係の変数には `VITE_` を付けない（上の表のとおり）。

---

## 動かし方（移行後）

ダブルクリックで起動するなら `start.bat`（デスクトップにも同じものとフォルダーのショートカットを置いてある）。詳しくは [docs/local_dev.md](docs/local_dev.md)。手で起動するなら：

```bash
cd D:\ct125-app
```

```bash
npm install
```

```bash
npm run dev
```

http://localhost:5173 を開く。`src/` を保存すると画面がすぐ変わる（ホットリロード）。

- dev サーバーは **localhost だけで待ち受ける**（`--host` を付けない）。付けると同じ Wi-Fi の端末から S3 の中身が見えてしまう
- データを新しくしたいとき：ct125-logger で `python -m ct125 export --upload` → ブラウザを再読み込み（cache を使っていれば `scripts/pull-data.ps1`）
- AWS の認証が切れていたら：プロファイル `ct125-logger` の鍵を確認してから `npm run dev` をやり直す（`docs/local_dev.md` の「困ったとき」）
