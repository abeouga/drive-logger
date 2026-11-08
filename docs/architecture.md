# 構成図（2026-11-09 時点）

実線＝実装済み、点線＝設計のみ（今後の拡張）。

> **作り直し（2026-11-09）**：データの流れを、S3 を中心にした 1 本にした（Epic #1）。バケットを役割ごとに分け、
> 処理の記録・走行の台帳・走行の分類・モデルの記録を足した。設計は [data_flow_design.md](data_flow_design.md)、
> 本番に入れる手順は [migration_split_buckets.md](migration_split_buckets.md)。

```mermaid
flowchart LR
    subgraph bike[バイク側]
        GPS[ATGM336H GPS<br/>9600bps・1Hz] --> ESP[ESP32<br/>CT125_LOGGER_V3.2]
        ACC[ADXL345 振動<br/>400Hz・±16g] --> ESP
        ESP --> SD[(microSD<br/>accel.csv / gps.csv / ...)]
    end

    subgraph cloud[AWS（ap-northeast-1）]
        DEVAPI[Lambda デバイス API<br/>機器トークン] -->|署名付き URL| ESP
        ESP -->|走行後に Wi-Fi で PUT| RAW[(S3 生データ<br/>ct125-logger-raw)]
        DEVAPI -->|完了の印| RAW
        RAW -->|S3 イベント| PIPE[Lambda コンテナ ct125-ride-pipeline<br/>前処理 → 分類 → 推論 → 書き出し]
        PIPE <--> WORK[(S3 作業用 ct125-logger-work<br/>runs/ 処理の記録と結果<br/>models/ モデルと model.json<br/>ledger/ 走行の台帳)]
        PIPE -->|公開の仕組み<br/>台帳が指す結果だけ| PUBLIC[(S3 公開用 ct125-logger-public<br/>datasets/shared/)]
        RETRAIN[手動: retrain・publish] -.-> PIPE

        CF[CloudFront<br/>drive.herdio-system.com] -->|/*| WEBAPP[(S3 webapp/<br/>React)]
        CF -->|/api/*| APIGW[API Gateway<br/>JWT 検証] --> DATAAPI[Lambda データ API<br/>FastAPI] --> PUBLIC
        COGNITO[Cognito<br/>ログイン] -.->|アクセストークン| APIGW
    end

    LOCAL[PC の CLI<br/>同じ処理の流れ] -->|読む| RAW
    LOCAL <-->|作業用だけ| WORK
    LOCAL -.->|公開を頼む| PIPE
    USER[ブラウザ] --> CF
    USER --> COGNITO
    WORK -.->|将来| SM[SageMaker で学習]
```

## 実装したもの

| 段階 | 実装 | 場所 |
|---|---|---|
| 記録・送信 | ESP32 Arduino スケッチ（V3.1）。GPS と加速度を別 CSV、時計は `t_us`。走行後に Wi-Fi でデバイス API から S3 へ送る | `firmware/ct125_logger/`、`api/`（デバイス API） |
| 読み込み・時刻 | `t_us` と GPS UTC の対応付け、JST | `pipeline/src/ct125/io.py` |
| クリーニング | 重複・振り切れ、GPS の status/sats/hdop/飛び/速度不整合 | `pipeline/src/ct125/clean.py` |
| 特徴量 | 1 秒窓の振動特徴量、帯域比 | `pipeline/src/ct125/features.py` |
| GPS 結合 | 速度の平滑化、窓中心への補間 | `pipeline/src/ct125/gps.py` |
| 前処理の本体 | 上の 4 つを 1 走行分まとめる（CLI と Lambda の両方から使う） | `pipeline/src/ct125/processing.py` |
| スコア | 速度補正ベースライン、Isolation Forest。学習（`fit_models`）と推論（`apply_models`）を分けてある | `pipeline/src/ct125/model.py` |
| 画面用データ | rides.json・ride_<id>.json・スペクトログラム・生波形。1 走行ずつ書き出せる（`export_ride`） | `pipeline/src/ct125/export.py`・`spectro.py` |
| 走行の分類 | 机上・停車・実走・実走（GPS なし）。学習に使う走行と、画面に出す走行を決める | `pipeline/src/ct125/classify.py` |
| 処理の流れ | process・retrain・publish。ローカルの CLI と Lambda が同じものを呼ぶ。処理の記録（run.json）・走行の台帳・モデルの記録（model.json） | `pipeline/src/ct125/flow.py`・`records.py`・`models.py`・`storage.py` |
| AWS の処理 | 生データが届いたら Lambda（コンテナ）が処理して公開。手動で学習し直し・公開 | `pipeline/src/ct125/cloud/`、`pipeline/deploy/lambda/`、`pipeline/scripts/build-pipeline-image.ps1` |
| 公開 | CloudFront＋Cognito ログイン＋データ API（FastAPI） | `web`（フロントと `api/`） |
| AWS のリソース | S3（画面・生データ・作業用・公開用）・CloudFront・Cognito・API Gateway・Lambda×3・ECR・ACM・IAM（ローカルの処理のロール）（Terraform） | `infra` |

## 自宅の位置

自宅の位置は見えてもよいと決めた（2026-11-09、#13）。前は自宅周辺 300 m の窓の座標を書き出さず、SSM に置いた地点で書き出した後に検査していたが、その仕組みは外した。

## 設計のみ（今後）

- SageMaker での学習（今は Lambda の `retrain` で十分な量。データが増えたら移す）
- ユーザーごとのデータセット（入口は `api\src\ct125_api\services\dataset_resolver.py`。今は全員 shared）
- ECU 系統：端子・電圧・プロトコルが未検証で安全に検証できないと判断し、触れていない
