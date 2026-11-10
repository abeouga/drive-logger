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
| 読み込み・時刻 | SD の CSV、`t_us` と GPS UTC の対応付け、JST | `src/ct125/io.py` |
| クリーニング | 重複・振り切れ、GPS の status/sats/hdop/飛び/速度不整合 | `src/ct125/clean.py` |
| 特徴量 | 1 秒窓の振動特徴量（RMS・p2p・crest・jerk・帯域比） | `src/ct125/features.py` |
| GPS 結合 | 速度の平滑化、窓の中心への補間 | `src/ct125/gps.py` |
| 前処理の本体 | 上の 4 つを 1 走行分まとめる（ファイルを読み書きしない） | `src/ct125/processing.py` |
| 走行の分類 | 机上・停車・実走・実走（GPS なし）。学習と画面に出すかを決める | `src/ct125/classify.py` |
| スコア | 速度で補正した正常時のベースライン（5 km/h ビンの中央値・MAD）からの逸脱 `z_speed` と、振動特徴量に速度を足した Isolation Forest `score_if`（しきい値は学習データのスコアの分位点）。画面の判定にどちらを使うかは config の `model.anomaly_method` | `src/ct125/model.py` |
| 画面用データ | rides.json・ride_<id>.json・スペクトログラム・生波形（記憶の上で作る） | `src/ct125/export.py`・`spectro.py` |
| 処理の流れ | process・retrain・publish。ローカルの CLI と Lambda が同じものを呼ぶ | `src/ct125/flow.py` |
| 記録 | 処理の記録（run.json）・走行の台帳・モデルの記録（model.json・notes.md） | `src/ct125/records.py`・`models.py` |
| 保存の口 | S3 と、テスト用の記憶の上の置き場所。生データ・作業用・公開用の 3 つの場所 | `src/ct125/storage.py` |
| AWS の入口 | Lambda（コンテナ）。イベントを命令に読み替えて、処理の流れを呼ぶ | `src/ct125/cloud/`、`deploy/lambda/` |

設計は [../docs/data_flow_design.md](../docs/data_flow_design.md)。ファイルの形は [../contracts/](../contracts/)。

健康な車両の走行データだけで学習している。故障データは含まれていないので、スコアは「速度で補正した正常時のベースラインからの逸脱」であり、故障の予測ではない。
ECU / K-Line 接続はスコープ外（端子・電圧・プロトコルが未検証で、今は安全に検証できないと判断）。

## セットアップ

```bash
uv venv --python 3.12
```

```bash
uv pip install -e ".[dev]"
```

ライブラリの版は `pyproject.toml` で固定している（Lambda のコンテナの `deploy/lambda/requirements.txt` と同じ。学習済みモデルを同じ版で読むため）。

## テスト

S3 には繋がない（記憶の上の置き場所で、処理の流れを端から端まで確かめる）。

```bash
.venv/Scripts/python.exe -m pytest -q
```

## 処理の流れ

| 命令 | どこで | すること |
|---|---|---|
| process | Lambda（生データに `upload_complete.json` が置かれたとき）／ローカル | 前処理 → 分類 → 今のモデルで点数付け → 画面用の書き出し → 作業用に保存 → 記録 → 台帳 |
| retrain | Lambda（手で）／ローカル | 停車・実走で消していない走行だけで学習 → 新しいモデル → 全走行を点数付けし直す |
| publish | Lambda だけ | 台帳が指す結果から、公開用（画面が読む場所）を作り直す |

- Lambda の process・retrain は、終わったら公開する（retrain は今使うモデルも切り替える）
- **ローカルの process・retrain は、作業用に結果と記録を置くだけ**。画面と、今使うモデルは変えない。公開するときは Lambda に頼む（下の publish）
- 処理ごとに `runs/<run_id>/run.json` が残る（失敗も理由と一緒に）。走行の台帳 `ledger/rides.json` が、走行ごとに「公開中の結果」を指す
- 学習のたびに `models/<版>/model.json`（使った走行・使わなかった理由・設定・コミット・ライブラリの版）と `notes.md` が残る。読むときにライブラリの版を突き合わせ、違えば止める

### ローカルで流す

S3 から生データを読み、作業用の場所に書く（手元にデータのフォルダーは置かない）。プロファイルは `config/default.yaml` の `aws`（`config/local.yaml` で上書き）。

```bash
.venv/Scripts/python.exe -m ct125 process --ride ride_20261108_011304
```

```bash
.venv/Scripts/python.exe -m ct125 retrain
```

結果を画面に出す（処理の Lambda に公開を頼む。学習し直しの結果なら、今使うモデルも切り替わる）：

```bash
.venv/Scripts/python.exe -m ct125 publish --run <処理の ID>
```

走行の台帳を見る：

```bash
.venv/Scripts/python.exe -m ct125 rides
```

### Lambda で流す

全走行で学習し直して公開する：

```bash
aws lambda invoke --function-name ct125-ride-pipeline --cli-binary-format raw-in-base64-out --payload '{"action":"retrain"}' --cli-read-timeout 900 --profile ct125-logger out.json
```

コードを変えたら、コンテナを作り直して ECR に上げ、Terraform で Lambda を切り替える（作業用・公開用のバケットが Terraform に無いと、スクリプトが止める）：

```powershell
./scripts/build-pipeline-image.ps1
```

```bash
terraform -chdir=infra apply
```

## 機器の登録と、PC から SD の走行を送る

機器（ESP32・PC）のトークンを作り、ハッシュだけを SSM に登録する（ESP32 のトークンは ESP32 に入れたら消す。設計は [../docs/device_upload_design.md](../docs/device_upload_design.md)）：

```bash
.venv/Scripts/python.exe -m ct125 register-device --id d01 --token-file d01.token
```

PC から SD の走行を送る（ESP32 と同じデバイス API を通す。走行 ID はサーバーが付ける）。PC の機器 ID とトークンは `config/default.yaml` の `upload`（既定は `pc01` と `config/pc01.token`。トークンはコミットしない）：

```bash
.venv/Scripts/python.exe -m ct125 register-device --id pc01 --token-file config/pc01.token
```

```bash
.venv/Scripts/python.exe -m ct125 upload-sd E:/sessions
```

- 走行のフォルダー 1 つでも、`/sessions` のような親フォルダーでもよい（`accel.csv` のあるフォルダーを送る）
- **同じ SD の走行は 2 回受け付けない**（#14）：SD のセッション名と、必須のファイル（accel・gps・meta）の大きさが同じなら同じ走行とみなす。ESP32 が送った走行を PC から送り直しても、走行は増えない（「送り終えている走行です」と出る）
- 途中で切れたら、出た走行 ID を `--resume <走行 ID>` に付けて送り直す

## 構成

`src/ct125/` にパイプライン（PC から送る道具は `device_upload.py`）、`tools/` は SD の点検（`check_session.py`・`analyze_timing.py`・`ride.py`）。
`notebooks/` は最初の解析の記録（作り直しの前の手元の `data/` で流したもの。今は流さない）。
AWS 上で動かす部分は `src/ct125/cloud/` と `deploy/lambda/`。`config/local.yaml` はコミットしない。
