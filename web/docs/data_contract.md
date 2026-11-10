# データの約束事（公開用のバケットの `datasets/<データセット>/`）

このアプリが読むデータの形（走行の一覧は `GET /api/rides`。形は `contracts/api/rides.schema.json`。各走行の `summary` は下の `rides.json` の 1 件と同じ形）。正式な定義は [contracts/app/](../../contracts/app/)（JSON Schema）と見本 `contracts/examples/app/`。作る側は `pipeline/` の `src/ct125/export.py`・`spectro.py`、読む側の型は `src/lib/types.ts`。pipeline のテストが書き出しを定義に当て、`src/lib/contract.check.ts`（型チェック）が見本を型に当てる。**3 つは同じ形に保つ。** 形を変えるときは contracts の定義の `version` を上げ、作る側と使う側を同じ PR で直す。公開中のデータは古い形のまま残るので、変えた後は全走行を処理し直して公開し直す（2026-11-10、#71 で `highlight` を `anomaly` にしたときから。前は「`app/v2/` を作る」としていたが、置き場所が `datasets/` になってからは使っていない）。

## 置き場所とファイル

```
s3://ct125-logger-public-<アカウントID>/datasets/shared/   （今は全ユーザー共通の shared だけ）
├── rides.json               走行一覧
├── ride_<id>.json           1 秒窓の列
├── spec_<id>.png            スペクトログラムの画像
├── spec_<id>.json           その説明
└── wave_<id>_<chunk>.json   1 秒窓の生波形（全部の窓を約 1 分ごとのファイルに分けたもの）
```

`<id>` は走行 ID そのもの（例 `ride_004`）。なので実際のファイル名は `ride_ride_004.json`・`spec_ride_004.png` のようになる。ファイル名に使える文字は `A-Z a-z 0-9 _ . -`（先頭は `.` 以外）。dev サーバーはそれ以外を 400 で断る。

文字コードは UTF-8。JSON の `NaN` は使わず、欠けている値は `null`。

## 位置情報の決まり

- GPS のない窓（補間できなかった窓）は、`lat`・`lon` を `null` にして書き出す
- 自宅周辺の窓にも座標を入れる（2026-11-09 に、自宅の位置は見えてもよいと決めた。前は自宅周辺 300 m の窓を `null` にし、`is_private`・`n_private` を出していた）

## `rides.json`

```ts
{ generated_at_ms: number; rides: RideSummary[] }
```

| キー | 型 | 意味 |
|---|---|---|
| `id` | string | 走行 ID（`ride_004`） |
| `start_ms` | number \| null | 記録開始の UNIX ミリ秒。GPS なしは null |
| `duration_s` | number | 記録の長さ（秒） |
| `distance_km` | number | GPS のある窓をつないだ距離 |
| `max_speed_kmh` | number \| null | 品質フィルター後の最高速度 |
| `fix_ratio` | number | GPS が有効な窓の割合 0〜1 |
| `gps` | `"full"` \| `"partial"` \| `"none"` | 0.95 以上／0.10 以上／未満 |
| `n_windows` | number | 1 秒窓の数 |
| `n_anomalies` | number | いつもと違う振動の窓の数。しきい値を超えた窓だけで、上位 N 件で埋めない。判定しない走行は 0 |
| `anomaly_method` | `"speed_baseline"` \| `"none"` | 判定の方法（下の `ride_<id>.json` の `anomaly.method` と同じ）。0 件が「判定して無かった」のか「判定していない」のかはこれで見分ける |
| `n_anomaly_z` / `n_anomaly_if` | number | z_speed > 3 の窓数／Isolation Forest が外れとした窓数 |
| `n_clipped` | number | ±16 g に達したサンプルを含む窓数 |
| `rms_median` | number | rms の中央値（g） |
| `spark` | (number \| null)[] | rms を 60 区間に平均したもの（カードの小さなグラフ） |
| `memo` | string | 本人のメモ（`memo.txt`・`readme.txt`） |

## `ride_<id>.json`

```ts
{ id: string; n: number; has_abs_time: boolean; anomaly: AnomalyInfo; columns: RideColumns }
```

`anomaly` は「いつもと違う振動」の判定のしかた。画面は `method` と `columns.anomaly` だけを読み、どのモデルで判定したかは気にしない（モデルを差し替えても画面を直さずに済むように）。

| キー | 型 | 意味 |
|---|---|---|
| `method` | `"speed_baseline"` \| `"none"` | `speed_baseline`：速度で補正したベースラインからの逸脱（z_speed）がしきい値を超え、走行中（5 km/h 以上）の窓。`none`：判定しない（GPS がなく速度が分からない走行。Isolation Forest は速く走った所や静かすぎる所を拾うため、そのまま出さない） |
| `threshold` | number \| null | しきい値（config の `model.z_threshold`、今は 3）。`none` は null |
| `model_version` | string \| null | 点数付けに使ったモデルの版 |

`columns` の配列はどれも長さ `n`（1 秒窓の数）で、同じ添字が同じ窓。

| 列 | 型 | 単位・意味 |
|---|---|---|
| `t_rel` | number | 記録開始からの秒（窓の中心） |
| `t_abs_ms` | number[] \| null | 日本時間の UNIX ミリ秒。GPS なしの走行は列ごと null |
| `lat` / `lon` | number \| null | 小数 5 桁（約 1 m）。GPS なしは null |
| `speed` | number \| null | km/h（GPS の品質フィルター後、3 点の移動中央値） |
| `rms` / `log_rms` / `p2p` / `crest` | number \| null | 重力を引いた合成加速度の rms（g）・その対数・振れ幅（g）・波高率 |
| `z` | number \| null | z_speed。速度のない窓は null |
| `score_if` | number \| null | Isolation Forest のスコア（大きいほどまれ） |
| `band_1_5` / `band_5_15` / `band_15_40` | number \| null | 1〜40 Hz の合計に対する帯域の割合 |
| `has_gps` `is_stopped` `is_edge` `is_clipped` `is_anomaly_z` `is_anomaly_if` | boolean | 各フラグ（`is_stopped`＝5 km/h 未満、`is_edge`＝先頭・末尾 60 秒） |
| `anomaly` | boolean | いつもと違う振動の窓（`anomaly.method` で判定した結果。しきい値を超えた窓だけ） |
| `anomaly_score` | number \| null | 判定に使ったスコア（大きいほど外れ。`speed_baseline` なら z_speed）。判定しない窓は null |
| `cls` | number | 地図の線の色の段階 0〜4（座標のない窓は -1） |

## `spec_<id>.png` と `spec_<id>.json`

- PNG：8 bit のグレー＋アルファ。**列＝窓**（`ride_<id>.json` の添字と同じ順）、**行＝周波数**（上の行が高い周波数。1 行 1 Hz、0〜199 Hz）。**不透明度＝その周波数の強さ**（dB を走行の中で正規化し 16 段階）。色は付けていないので、表示側でテーマの色を当てる（`mask-image`）
- JSON：

| キー | 型 | 意味 |
|---|---|---|
| `id` | string | 走行 ID |
| `n_cols` | number | 画像の列数（＝窓の数） |
| `f_max_hz` | number | 200 |
| `window_sec` | number | 1 |
| `db_min` / `db_max` | number | 不透明度 0 と 1 にあてた dB |
| `pct` | [number, number] | その dB を決めた分位点（5, 99.5） |
| `peak_hz` | (number \| null)[] | 各窓で最も強い周波数（5 Hz 以上） |

## `wave_<id>_<chunk>.json`

```ts
{ id: string; unit: "mg"; chunk: number; windows: { i: number; fs: number; t0: number; ax: number[]; ay: number[]; az: number[] }[] }
```

全部の 1 秒窓の生波形を、窓の添字 `i` を 60 で割った商（`chunk`）ごとのファイルに分ける（1 秒窓なので約 1 分ずつ）。`<chunk>` は 3 桁の 0 詰めで、例えば `wave_ride_004_004.json` には `i` = 240〜299 が入る。画面は走行を開いたときには読まず、1 秒を選んだときに、その 1 秒を含むファイルだけを読む（一度読んだ分は覚えておく。分け方は `src/lib/wave.ts` と pipeline の `export.WAVE_CHUNK_WINDOWS`）。記録の先頭・末尾の 60 秒の窓や GPS の無い窓も書き出す。ファイルが無いのは、加速度の記録が無い走行か、前の形で処理した走行（前は 1 走行 1 つの `wave_<id>.json` に、基準を超えた窓だけを書いていた。公開し直すと消える）。

大きさの目安：1 窓 約 4.7 KB、1 ファイル（60 窓）約 290 KB、14 分の走行で 14 ファイル・合計 約 3.9 MB（ride_20261109_030109 で測った値。30 分なら 約 8 MB）。

`i` は `ride_<id>.json` の添字、`t0` は窓の開始（記録開始からの秒）、`ax`〜`az` はその 1 秒の各軸から平均（≒重力）を引いた値（mg の整数）。軸はセンサー基板の軸のまま。
