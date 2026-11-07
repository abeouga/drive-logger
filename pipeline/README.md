# CT125 走行データロガー 解析パイプライン

ハンターカブ CT125（JA55）に載せた ESP32 ロガー（ATGM336H GPS ＋ ADXL345 加速度 ＋ microSD）の走行記録を、
ローカル解析 → 地図・タイムライン可視化 → AWS（S3）保管・配信 へつなぐポートフォリオ。

- 計画：[docs/DEV_PLAN.md](docs/DEV_PLAN.md)（表現上の制約 4. と作業ルール 7. を全成果物に適用）
- データの実測スキーマ：[docs/data_schema.md](docs/data_schema.md)
- 未確定事項・質問：[docs/QUESTIONS.md](docs/QUESTIONS.md)
- 進捗：[docs/PROGRESS.md](docs/PROGRESS.md)
- ロガー本体：データ仕様 [docs/data_spec_v2.md](docs/data_spec_v2.md)、開発記録 [docs/dev_log_hardware.md](docs/dev_log_hardware.md)、配線図 [docs/hardware/配線図/](docs/hardware/配線図/)、SD の点検スクリプト `tools/`（`check_session.py`・`analyze_timing.py`・`ride.py`）

## 現在の状態（2026-11-06、フェーズ 3 完了）

- 2026-11-02 に実車で記録した 9 本（`data/raw/ride_001`〜`ride_009`、コミット対象外）を棚卸しし、列・単位・サンプリング周波数（約 398.5 Hz）・時刻基準・GPS 有効割合を確定した。
- CSV → クリーニング → 1 秒窓の振動特徴量（RMS・p2p・crest・jerk・帯域比）→ GPS 結合（速度・座標の補間、品質フィルタ）→ `windows.parquet` までがコマンド 1 つで再現できる。
- 速度で補正した正常時のベースライン（5 km/h ビンの中央値・MAD）からの逸脱 `z_speed` と、振動特徴量だけの Isolation Forest `score_if` を全窓に付けた。走行中に `z_speed > 3` の窓はなく、往路・復路で同じ場所の振動が一致するかは確認できなかった（`docs/PROGRESS.md`）。
- 走行ごとに地図（色付き軌跡＋マーカー）とタイムラインの静的 HTML を `web/` に生成する。GPS が取れなかった走行は地図を出さず、注意書きとタイムラインだけを出す。
- Web アプリ版（地図・タイムライン・スペクトログラムが連動する画面）は別リポジトリ `D:/ct125-app`。https://drive.herdio-system.com/ で公開（ログイン必須）。
- **AWS 上で自動処理（2026-11-07）**：`upload --parts raw` で生データを S3 に上げると、Lambda（コンテナ、`src/ct125/cloud/`）が前処理 → 学習済みモデルで点数付け → 画面用データの書き出し → 座標検査まで行い、公開ページに出る。学習し直しも Lambda で行える（下の「AWS 上の処理」）。
- 取り付けは暫定（ブレッドボードを車体に置いただけ）。20 Hz 以上の帯域には置き方の共振が混ざる可能性がある。
- 前処理・時刻同期・傾き・振動・GPS についての知見は [docs/knowledge_preprocessing.md](docs/knowledge_preprocessing.md)。構成図は [docs/architecture.md](docs/architecture.md)。
- S3 バケット（東京、非公開）は Terraform（`D:\ct125-logger-terraform`）で作成済み。アップロードと署名付き URL のコマンド（`upload` / `share`）と手順は [docs/aws_setup.md](docs/aws_setup.md)。走行データと走行ページは自宅マスクを適用してから上げる。
- 健康な車両の走行データのみ。故障データは含まれていないため、この先作る異常スコアは「速度で補正した正常時のベースラインからの逸脱」であり、故障の予測ではない。
- ECU / K-Line 接続はスコープ外（端子・電圧・プロトコルが未検証で期限内に安全に検証できないと判断）。GPS と振動の 2 系統でパイプラインを作る。

## セットアップ

```bash
uv venv --python 3.12
```

```bash
uv pip install -e ".[dev]"
```

## 使い方

全走行を処理して `data/processed/<ride_id>/windows.parquet` を作る：

```bash
.venv/Scripts/python.exe -m ct125 process --all
```

1 本だけ：

```bash
.venv/Scripts/python.exe -m ct125 process --ride ride_004
```

異常スコアを付ける（全走行の windows.parquet で学習し、`scored.parquet` と `data/models/<日付>/` を出力）：

```bash
.venv/Scripts/python.exe -m ct125 score
```

地図とタイムラインの HTML を作る（`web/index.html` から各走行へ）：

```bash
.venv/Scripts/python.exe -m ct125 render
```

`config/local.yaml` を置いていない場合、地図ページに「マスク未適用」の警告が出る。その状態の HTML は公開・アップロードしない。

テスト：

```bash
.venv/Scripts/python.exe -m pytest -q
```

自宅などをマスクするには `config/local.example.yaml` を `config/local.yaml` にコピーして座標を書く（コミットされない）。

## AWS 上の処理

新しい走行を公開する（生データを S3 に上げるだけ。最後に `upload_complete.json` を置き、それを合図に Lambda が処理する）：

```bash
.venv/Scripts/python.exe -m ct125 upload --ride ride_010 --parts raw
```

全走行で学習し直して、全走行を書き出し直す（新しい版のモデルを `models/<日時>/` に置き、`models/current.json` を切り替える）：

```bash
aws lambda invoke --function-name ct125-ride-pipeline --cli-binary-format raw-in-base64-out --payload '{"action":"retrain"}' --cli-read-timeout 900 --profile ct125-logger out.json
```

マスクする地点（`config/local.yaml`）を変えたら、AWS 側にも反映する（座標だけを SSM の SecureString に上げる）：

```bash
.venv/Scripts/python.exe -m ct125 sync-private-points
```

コードを変えたら、コンテナを作り直して ECR に上げ、Terraform で Lambda を切り替える：

```powershell
./scripts/build-pipeline-image.ps1
```

```bash
terraform -chdir=D:/ct125-logger-terraform apply
```

- コンテナは `deploy/lambda/Dockerfile`。学習済みモデル（pickle）を読むため、ライブラリの版は `.venv` と同じに固定している（`deploy/lambda/requirements.txt`）。版を上げたら `retrain` する
- 仕組みと自宅座標の扱いは [docs/architecture.md](docs/architecture.md)

ノートブックの実行：

```bash
.venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_inspect.ipynb
```

## 構成

計画書 6. のとおり（`src/ct125/` にパイプライン、`notebooks/` は確認用、`web/` は生成物、`data/raw/`・`config/local.yaml` はコミットしない）。
AWS 上で動かす部分は `src/ct125/cloud/`（役割ごとのファイルの説明は `src/ct125/cloud/__init__.py`）と `deploy/lambda/`。
