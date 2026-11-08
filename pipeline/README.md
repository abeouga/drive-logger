# pipeline：解析パイプライン（Python）

ESP32 ロガー（ATGM336H GPS ＋ ADXL345 加速度 ＋ microSD）の走行記録を、
前処理 → 1 秒窓の特徴量 → 異常スコア → 画面用データ（JSON・PNG）にする。
同じコードを、ローカルの CLI と AWS の Lambda（コンテナ）の両方から使う。

- 計画：[../docs/DEV_PLAN.md](../docs/DEV_PLAN.md)（表現上の制約 4. と作業ルール 7. を全成果物に適用）
- データの実測スキーマ：[../docs/data_schema.md](../docs/data_schema.md)、データ仕様：[../docs/data_spec_v2.md](../docs/data_spec_v2.md)
- 前処理の知見：[../docs/knowledge_preprocessing.md](../docs/knowledge_preprocessing.md)、構成：[../docs/architecture.md](../docs/architecture.md)
- 作り直しの設計（S3 を中心にした 1 本の流れ）：[../docs/data_flow_design.md](../docs/data_flow_design.md)
- 進捗：[../docs/PROGRESS.md](../docs/PROGRESS.md)

## 中身

| 段階 | 内容 | 場所 |
|---|---|---|
| 読み込み・時刻 | `t_us` と GPS UTC の対応付け、JST | `src/ct125/io.py` |
| クリーニング | 重複・振り切れ、GPS の status/sats/hdop/飛び/速度不整合 | `src/ct125/clean.py` |
| 特徴量 | 1 秒窓の振動特徴量（RMS・p2p・crest・jerk・帯域比） | `src/ct125/features.py` |
| GPS 結合 | 速度の平滑化、窓の中心への補間 | `src/ct125/gps.py` |
| 前処理の本体 | 上の 4 つを 1 走行分まとめる | `src/ct125/processing.py` |
| スコア | 速度で補正した正常時のベースライン（5 km/h ビンの中央値・MAD）からの逸脱 `z_speed` と、振動特徴量だけの Isolation Forest `score_if` | `src/ct125/model.py` |
| 画面用データ | rides.json・ride_<id>.json・スペクトログラム・生波形 | `src/ct125/export.py`・`spectro.py` |
| AWS の処理 | S3 に生データが届いたら Lambda が前処理 → 点数付け → 書き出し → 公開。手で学習し直し | `src/ct125/cloud/`、`deploy/lambda/` |

健康な車両の走行データだけで学習している。故障データは含まれていないので、スコアは「速度で補正した正常時のベースラインからの逸脱」であり、故障の予測ではない。
ECU / K-Line 接続はスコープ外（端子・電圧・プロトコルが未検証で、今は安全に検証できないと判断）。

## セットアップ

```bash
uv venv --python 3.12
```

```bash
uv pip install -e ".[dev]"
```

## テスト

```bash
.venv/Scripts/python.exe -m pytest -q
```

## AWS 上の処理

新しい走行は、機器（ESP32）がデバイス API から S3 に送る。最後に `upload_complete.json` が置かれ、それを合図に Lambda が処理する。

全走行で学習し直して、全走行を書き出し直す（新しい版のモデルを `models/<日時>/` に置き、`models/current.json` を切り替える）：

```bash
aws lambda invoke --function-name ct125-ride-pipeline --cli-binary-format raw-in-base64-out --payload '{"action":"retrain"}' --cli-read-timeout 900 --profile ct125-logger out.json
```

コードを変えたら、コンテナを作り直して ECR に上げ、Terraform で Lambda を切り替える：

```powershell
./scripts/build-pipeline-image.ps1
```

```bash
terraform -chdir=infra apply
```

- コンテナは `deploy/lambda/Dockerfile`。学習済みモデル（pickle）を読むため、ライブラリの版は `.venv` と同じに固定している（`deploy/lambda/requirements.txt`）。版を上げたら `retrain` する

## 機器の登録

ESP32 の機器トークンを作り、ハッシュだけを SSM に登録する（トークンはファイルに書き、ESP32 に入れたら消す。設計は [../docs/device_upload_design.md](../docs/device_upload_design.md)）：

```bash
.venv/Scripts/python.exe -m ct125 register-device --id d01 --token-file d01.token
```

ESP32 のふりをして 1 走行分を送る（ファームウェアと同じ手順のお手本）：

```bash
.venv/Scripts/python.exe tools/device_upload_simulator.py <走行のフォルダー> --device-id d01 --token-file d01.token
```

## ローカルの CLI（作り直しの途中）

`process`（前処理）→ `score`（学習と点数付け）→ `export`（画面用の書き出し）を、`data/` の上で流せる。
`upload` は `data/` の raw・processed・models を S3 に上げる。
ローカルも「S3 から読み、S3 に書く」1 本の流れにする作り直しを進めている（#8。設計は [../docs/data_flow_design.md](../docs/data_flow_design.md)）。

```bash
.venv/Scripts/python.exe -m ct125 process --all
```

```bash
.venv/Scripts/python.exe -m ct125 score
```

```bash
.venv/Scripts/python.exe -m ct125 export
```

## 構成

`src/ct125/` にパイプライン、`notebooks/` は確認用、`tools/` は SD の点検（`check_session.py`・`analyze_timing.py`・`ride.py`）と機器のお手本（`device_upload_simulator.py`）。
AWS 上で動かす部分は `src/ct125/cloud/`（役割ごとのファイルの説明は `src/ct125/cloud/__init__.py`）と `deploy/lambda/`。
`data/`・`config/local.yaml` はコミットしない。
