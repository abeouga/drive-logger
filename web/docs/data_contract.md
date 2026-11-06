# データの約束事（S3 の `app/v1/`）

このアプリが読むデータの形。作る側は ct125-logger の `python -m ct125 export`（`src/ct125/export.py`・`spectro.py`）、読む側の型は `src/lib/types.ts`。**3 つは同じ形に保つ。** 形を変えるときは `app/v2/` を作り、古いアプリが壊れないようにする。

## 置き場所とファイル

```
s3://ct125-logger-<アカウントID>/app/v1/
├── rides.json               走行一覧
├── ride_<id>.json           1 秒窓の列
├── spec_<id>.png            スペクトログラムの画像
├── spec_<id>.json           その説明
└── wave_<id>.json           見どころの窓の生波形
```

`<id>` は走行 ID そのもの（例 `ride_004`）。なので実際のファイル名は `ride_ride_004.json`・`spec_ride_004.png` のようになる。ファイル名に使える文字は `A-Z a-z 0-9 _ . -`（先頭は `.` 以外）。dev サーバーはそれ以外を 400 で断る。

文字コードは UTF-8。JSON の `NaN` は使わず、欠けている値は `null`。

## 位置情報の決まり

- 自宅など登録地点の周辺 300 m（`is_private=true`）の窓と、GPS のない窓は、**`lat`・`lon` を `null` にして書き出す**（隠すのではなく、データに入れない）
- 登録地点の座標そのものはどのファイルにも入れない
- `export` は書き出した後に、`check-privacy` は配る前の HTML に、半径 300 m 以内の座標がないことを検査する

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
| `n_highlights` | number | 見どころの窓の数 |
| `highlight_basis` | `"z_speed>3"` \| `"z_speed_top"` \| `"score_if_top"` | 見どころの決め方 |
| `n_anomaly_z` / `n_anomaly_if` | number | z_speed > 3 の窓数／Isolation Forest が外れとした窓数 |
| `n_private` | number | 地図に出さない（自宅周辺の）窓数 |
| `n_clipped` | number | ±16 g に達したサンプルを含む窓数 |
| `rms_median` | number | rms の中央値（g） |
| `spark` | (number \| null)[] | rms を 60 区間に平均したもの（カードの小さなグラフ） |
| `memo` | string | 本人のメモ（`memo.txt`・`readme.txt`） |

## `ride_<id>.json`

```ts
{ id: string; n: number; has_abs_time: boolean; highlight_basis: HighlightBasis; columns: RideColumns }
```

`columns` の配列はどれも長さ `n`（1 秒窓の数）で、同じ添字が同じ窓。

| 列 | 型 | 単位・意味 |
|---|---|---|
| `t_rel` | number | 記録開始からの秒（窓の中心） |
| `t_abs_ms` | number[] \| null | 日本時間の UNIX ミリ秒。GPS なしの走行は列ごと null |
| `lat` / `lon` | number \| null | 小数 5 桁（約 1 m）。自宅周辺・GPS なしは null |
| `speed` | number \| null | km/h（GPS の品質フィルター後、3 点の移動中央値） |
| `rms` / `log_rms` / `p2p` / `crest` | number \| null | 重力を引いた合成加速度の rms（g）・その対数・振れ幅（g）・波高率 |
| `z` | number \| null | z_speed。速度のない窓は null |
| `score_if` | number \| null | Isolation Forest のスコア（大きいほどまれ） |
| `band_1_5` / `band_5_15` / `band_15_40` | number \| null | 1〜40 Hz の合計に対する帯域の割合 |
| `has_gps` `is_stopped` `is_edge` `is_private` `is_clipped` `is_anomaly_z` `is_anomaly_if` `highlight` | boolean | 各フラグ（`is_stopped`＝5 km/h 未満、`is_edge`＝先頭・末尾 60 秒） |
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

## `wave_<id>.json`

```ts
{ id: string; unit: "mg"; windows: { i: number; fs: number; t0: number; ax: number[]; ay: number[]; az: number[] }[] }
```

見どころの窓（`highlight=true`）だけ。`i` は `ride_<id>.json` の添字、`t0` は窓の開始（記録開始からの秒）、`ax`〜`az` はその 1 秒の各軸から平均（≒重力）を引いた値（mg の整数）。軸はセンサー基板の軸のまま。
