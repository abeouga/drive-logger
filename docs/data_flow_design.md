# データの流れの作り直し（設計）

- 状態：設計を決めた段階（2026-11-09）。実装は Epic #1 の子 Issue で進める
- 元になった決定：#2（S3 の構成と書ける人）、#3（走行の分類）
- 今の構成は [architecture.md](architecture.md)。この文書は「作り直した後の姿」を書く

## 1. ねらい

| 今の問題 | 作り直した後 |
|---|---|
| ローカル（`data/` の上で学習）と Lambda（S3 の上で推論）の 2 本の流れが、同じ本番の場所を書き換え合う | 処理は 1 本。ローカルでも Lambda でも、同じコードが S3 から読み、S3 に書く |
| `rides.json` の書き手が 3 つある（Lambda の差し替え・retrain・ローカルの `export --upload`） | 公開用に書けるのは「公開の仕組み」だけ |
| どの処理の結果を画面に出しているか分からない。前の結果に戻せない | 処理ごとに記録（`run.json`）を残し、台帳が「公開中の結果」を指す |
| 机上の試験も学習に入る | 走行を自動で分類し、学習に使う走行を台帳で選ぶ |
| モデルの作り方が残らない | 学習のたびに `model.json`（使った走行・設定・版）と `notes.md` を残す |

## 2. 全体の流れ

```mermaid
flowchart LR
    ESP[ESP32] -->|デバイス API| RAW[(生データ<br/>raw バケット)]
    PC[PC の SD] -->|デバイス API| RAW
    RAW -->|upload_complete.json| PIPE[処理<br/>Lambda]
    LOCAL[ローカルの CLI] -.同じコード.- PIPE
    RAW --> LOCAL
    PIPE --> WORK[(作業用<br/>work バケット<br/>runs/・models/・ledger/)]
    LOCAL --> WORK
    PIPE -->|公開の仕組み| PUB[(公開用<br/>public バケット)]
    PUB --> API[データ API] --> WEB[画面]
    API -->|消す・戻す・切り替え| WORK
```

## 3. バケット（#2 の決定 A：役割ごとに別のバケット）

| バケット | 名前 | 中身 | 書ける | 保存期間 |
|---|---|---|---|---|
| 生データ | `ct125-logger-raw-<アカウントID>` | 機器・PC から届いた CSV と meta.json。正本 | デバイス API だけ | 期限なし（消すのは #24 で決める） |
| 作業用 | `ct125-logger-work-<アカウントID>` | 処理の結果と記録（`runs/`）、モデル（`models/`）、走行の台帳（`ledger/`） | 処理（Lambda・ローカル）。台帳はデータ API も | 当面は期限なし（1 回の処理で 1 走行あたり約 0.3 MB と小さい。#24 で決める） |
| 公開用 | `ct125-logger-public-<アカウントID>` | 画面が読む JSON・PNG（公開中の結果だけ） | 公開の仕組み（処理の Lambda）だけ | 期限なし（いつでも作業用から作り直せる） |
| 画面 | `ct125-logger-<アカウントID>`（今のバケット） | React のビルド結果（`webapp/`）だけ | デプロイ（`web/scripts/deploy.ps1`） | — |

- どのバケットも、公開ブロック・SSE-S3・HTTPS のみ・バージョニング（古い版は 30 日）は今と同じ
- 今のバケットは名前を変えられないので、画面（CloudFront の配信元）用として残し、走行データは新しい 3 つに移す（12.）
- リージョンはプロジェクトのリージョン（ap-northeast-1）だけ

## 4. キーの置き方

```
raw バケット
  <ride_id>/accel.csv・gps.csv・events.csv・status.csv・meta.json・notes.md（または memo.txt）
  <ride_id>/upload_session.json   受け付けの記録（デバイス API）
  <ride_id>/upload_complete.json  完了の合図。これが置かれると処理が動く

work バケット
  runs/<run_id>/run.json                          処理の記録（6.）
  runs/<run_id>/rides/<ride_id>/windows.parquet   1 秒窓の特徴量
  runs/<run_id>/rides/<ride_id>/scored.parquet    点数付きの窓
  runs/<run_id>/rides/<ride_id>/summary.json      一覧用の要約（rides.json の 1 件）
  runs/<run_id>/rides/<ride_id>/app/              画面用のファイル（ride_・spec_・wave_）
  models/<version>/baseline.json・isolation_forest.pkl・model.json・notes.md
  models/current.json                             今使うモデルの版
  ledger/rides.json                               走行の台帳（7.）

public バケット
  datasets/shared/rides.json                      画面の走行一覧（台帳から作る）
  datasets/shared/ride_<id>.json・spec_<id>.png・spec_<id>.json・wave_<id>.json
```

- `run_id`：`<UTC の日時>-<6 桁の 16 進>`（例 `20261109T031500Z-3f9a1c`）。並べると時刻の順になる
- `version`（モデル）：`<UTC の日時>`（例 `20261109-031500`）。ローカルと Lambda でそろえる（今は YYYYMMDD と YYYYMMDD-HHMMSS が混ざっている）
- 画面用のファイル名と中身は今と同じ（[web/docs/data_contract.md](../web/docs/data_contract.md)）。画面とデータ API は、読む場所が変わるだけ
- キーの置き方は、コードの 1 か所（#4 の定義と、pipeline・api の設定）にだけ書く

## 5. 処理（1 本の流れ）

| 命令 | きっかけ | すること |
|---|---|---|
| process | raw に `upload_complete.json` が置かれた／手で走行を指定 | 生データ → 前処理 → 分類 → 今のモデルで点数付け → 画面用の書き出し → work に保存 → 台帳を更新 → 公開 |
| retrain | 手で | 台帳で「学習に使う」走行だけで学習 → 新しいモデルの版 → 全走行を点数付けし直す → 公開 → `current.json` を切り替え |
| publish | 処理の後／データ API（消す・戻す・切り替え）の後 | 台帳が指す結果から公開用を作り直す（8.） |

- 計算（前処理・分類・点数付け・書き出し）は、ファイルを読み書きしない関数にする。保存は「保存の口」（S3 版と、テスト用のメモリ版）を通す
- ローカルの CLI と Lambda は、同じ処理を呼ぶ。違うのは、保存の口に渡す認証情報と、`run.json` の `where`（`local` か `lambda`）だけ
- ローカルにデータのフォルダーは置かない。作業は一時フォルダーで行い、終わったら消す

## 6. 処理の記録（`run.json`）

処理 1 回ごとに 1 つ。失敗しても理由と一緒に残す（今は Lambda のログにしか残らない）。

```json
{
  "schema": "run/1",
  "run_id": "20261109T031500Z-3f9a1c",
  "action": "process",
  "where": "lambda",
  "commit": "288d04e",
  "started_at": "2026-11-09T03:15:00Z",
  "finished_at": "2026-11-09T03:15:19Z",
  "status": "succeeded",
  "error": null,
  "config": { "window_sec": 1.0, "classify": { "...": "..." }, "model": { "...": "..." } },
  "model_version": "20261107-143620",
  "rides": [
    { "ride_id": "ride_20261108_011304", "status": "succeeded", "kind": "idle", "kind_metrics": { "vib_median_g": 0.14, "gps_windows": 280, "max_dist_m": 12.0, "moving_windows": 0 }, "n_windows": 291, "n_highlights": 10, "error": null }
  ]
}
```

## 7. 走行の台帳（`ledger/rides.json`）

走行ごとに 1 件。React 用の `rides.json` は、ここから作る。

| 項目 | 中身 |
|---|---|
| `ride_id` | サーバーが付けた走行 ID（`ride_<日時>`） |
| `original_name` | 上げ直す前の名前（`ride_004` など）。無ければ null |
| `device_id`・`local_session` | 記録した機器と、SD のセッション名（同じ走行の 2 回目の送信を見分ける。#14） |
| `kind`・`kind_metrics` | 分類と、その理由の数値（9.） |
| `deleted`・`deleted_at`・`deleted_by` | 画面で消したか。消しても生データと処理の結果は残す |
| `published_run` | 公開中の処理の結果（`run_id`） |
| `runs` | この走行を処理した `run_id` の一覧（新しい順） |

- 書き手：処理（新しい結果ができたら `published_run` を最新に）とデータ API（消す・戻す・前の結果に戻す）
- 同時に書いても壊れないよう、S3 の条件付き書き込み（ETag が変わっていなければ書く。変わっていたら読み直してやり直す）で更新する。走行が数百件までなら 1 つの JSON で足りる

## 8. 公開の仕組み

- 台帳を読み、**画面に出す走行**（消していない・机上でない）について、`published_run` の画面用ファイルを work から public にコピーし、`rides.json` を作り直す。出さなくなった走行のファイルは public から消す
- public に書けるのはこの仕組みだけ（処理の Lambda の中で動く）。データ API は台帳を書き換えた後、処理の Lambda に `{"action": "publish"}` を非同期で渡す
- 前の結果に戻す ＝ 台帳の `published_run` を書き換えて publish。結果そのものは work に残っているので、計算し直さない

## 9. 走行の分類（#3 の決定 A：振動と GPS から自動で分類）

| 分類（`kind`） | 条件 | 画面 | 学習 |
|---|---|---|---|
| 机上（`desk`） | 振動の中央値が 0.05 g 未満（エンジンの振動が無い） | 出さない | 使わない |
| 停車（`idle`） | 振動があり、GPS のある窓が 60 以上で、始点から 200 m 以上動いていない | 出す | 使う |
| 実走（`ride`） | GPS で始点から 200 m 以上動き、5 km/h 以上の窓が 60 以上 | 出す | 使う |
| 実走（GPS なし）（`ride_nogps`） | 振動はあるが、GPS が足りなくて動いたか分からない | 出す | 使わない |

- 上から順に判定し、どれにも当たらないとき（GPS で 200 m 以上動いたが 5 km/h 以上の窓が少ない、など）は実走（GPS なし）にする（学習に使わない側に倒す）
- 「振動」は 1 秒窓の合成加速度の RMS（重力を除いたもの、`rms`）。手元の 9 走行では、エンジン停止 約 0.015 g、アイドリング 約 0.13〜0.16 g、走行中 0.3 g 以上
- 手元の 9 走行での確かめ（2026-11-09）：ride_006 は机上（0.015 g）、ride_001〜003 は停車（GPS の窓 84〜124、始点から 4〜19 m）、ride_004・005 は実走（約 2.3 km、5 km/h 以上の窓 468・543）、ride_007〜009 は実走（GPS なし）
- しきい値は `pipeline/config/default.yaml` の `classify` に置く。変えたら全走行を分類し直す
- 画面で消した走行は、分類にかかわらず学習に使わない
- 分類の結果と理由の数値を、台帳と `run.json` に残す

## 10. モデルの記録（#11）

`models/<version>/model.json`：版・日時・ローカルか Lambda か・コミット・ライブラリの版・設定・学習に使った走行と窓の数・使わなかった走行と理由・結果の要約（ベースラインのビンの数、異常の候補の数）。
`models/<version>/notes.md`：要約を自動で書き、気づいたことを人が足す。
モデルを読むときに、学習したときのライブラリの版と突き合わせ、違えば止める（pickle の読み込みは版がずれると壊れることがある）。

## 11. 権限

| 誰 | raw | work | public | そのほか |
|---|---|---|---|---|
| デバイス API | 書く（署名付き URL）・受け付けの記録を読む | — | — | 機器のトークンのハッシュ（SSM）を読む |
| 処理の Lambda | 読む | 読む・書く | 書く | — |
| データ API | — | 台帳を読む・書く。`run.json` と `models/` を読む | 読む | 処理の Lambda を呼ぶ（publish だけ） |
| ローカルの処理（PC） | 読む | 読む・書く | **書けない** | — |
| デプロイ（PC の管理者） | すべて | すべて | すべて | Terraform を流す |

- ローカルの処理は、書ける範囲を絞った IAM ロール（`ct125-local-pipeline`）を、PC の CLI プロファイルから引き受けて使う。今の管理者のプロファイル（`ct125-logger`）は Terraform とデプロイにだけ使う
- 人のログイン（AWS Settings で管理）には手を加えない。ロールはこの処理のためだけに作る

## 12. 今のバケットからの移し方（#6・#15）

本番の画面を止めずに移す。どの段階でも、前の段階に戻せる。

1. Terraform で raw・work・public を足す（今のバケットには触らない）
2. 今の `raw/ride_001`〜`009` を raw バケットにコピーする（今のバケットの中身は消さない）
3. 新しい処理のコンテナを作り、Lambda を入れ替える。デバイス API の書き先と S3 のイベントを raw バケットに向ける
4. 9 走行を処理し直して、public に公開する。データ API の読み先を public に向け、画面で今と同じに見えることを確かめる
5. 9 走行をデバイス API から上げ直し（#15）、台帳に元の名前を残す
6. 今のバケットの古い場所（`raw/`・`processed/`・`models/`・`app/`・`site/`）を消すかを決める（消すのは本人の了承の後）

## 13. まだ決めていないこと

| 項目 | 案 | 決める場所 |
|---|---|---|
| ローカルで出した結果を公開するか | 案：ローカルの処理は work に結果を置くだけで、自動では公開しない。公開するときは `python -m ct125 publish --run <run_id>` で処理の Lambda に頼む（本番の画面を変えるのは、いつも同じ Lambda になる） | #10（本人と相談） |
| 走行を本当に消す方法と保存期間 | — | #24 |
| モデルの保存形式と、models/ に書ける人 | — | #23 |
| 利用者・機器ごとのデータの分け方 | 今は全員が `datasets/shared/` | #25 |
| test 環境 | — | #26 |
