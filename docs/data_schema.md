# データスキーマ（最初の 9 走行の実測）

- 最初の 9 走行（2026-11-02 に実車で記録した `ride_001`〜`ride_009`。SD から写した原本）を、2026-11-06 に測った当時の記録。ファームウェアの版はそのときの V2.1（今の版は [firmware/ct125_logger/README.md](../firmware/ct125_logger/README.md)）
- 6. の判定値は、今も `pipeline/config/default.yaml` の値の根拠
- 元になる仕様：[data_spec_v2.md](data_spec_v2.md)（v2）。本書は **実データで確認できた事実** を書く。記録の前の見込みと食い違う点は「実測」として明記する
- 位置情報の方針：緯度・経度の実値はこの文書・ノートブック・リポジトリに書かない（範囲の確認結果だけを書く）

---

## 1. ファームウェア（当時の `firmware/ct125_logger/ct125_logger.ino` を読んで確定）

| 項目 | 実測・確認結果 | 記録の前の見込みとの差 |
|---|---|---|
| 言語・環境 | **Arduino**（ESP32 Arduino core 3.3.12、arduino-cli 1.5.2 でビルド）。版は `CT125_LOGGER_V2.1`（`meta.json` の `firmware`、`events.csv` の `boot` 行と一致） | 「Arduino か ESP-IDF か未確認」→ Arduino で確定 |
| GPS | ATGM336H、UART2（RX=IO32、TX=IO33）、**9600bps**、NMEA。`$..RMC` と `$..GGA` を使い、RMC 1 文ごとに `gps.csv` に 1 行（**1Hz**、実測の行間隔の中央値 1.000〜1.001 s）。チェックサム不一致の文は捨てる。PPS は未接続（`PIN_PPS=-1`） | 推定どおり |
| ADXL345 | I2C **0x53**（SDO=GND）、I2C 400kHz。`DATA_FORMAT=0x0B`（**FULL_RES、±16g**）、`BW_RATE=0x0C`（**ODR 400Hz**。V3.5 からは `0x0D`＝ODR 800Hz）、FIFO ストリームモード。生 LSB × **0.0039 g/LSB** で g に変換して書く（CSV の値は 0.0039 の整数倍。小数 4 桁） | 「レンジ・ODR 未確認」→ ±16g・400Hz で確定 |
| SD 書き込み | SPI（CS=IO5）。電源オンごとに `/sessions/ride_NNN/` を作り、CSV 4 種＋`meta.json`。1 秒ごとに flush。加速度はコア 0 のタスクが FIFO から読み、リングバッファ経由でコア 1 の `loop()` が書く | — |
| 時刻の生成 | すべて **`t_us` ＝ ESP32 `esp_timer_get_time()`（起動からのマイクロ秒、64bit）**。RTC なし。加速度の `t_us` は V2.1 の PLL 方式（前サンプル＋周期で進め、FIFO を読んだ時刻とのずれを少しずつ戻す）。GPS 行の `t_rx_us` は RMC 文の先頭 `$` を受けた時刻。UTC への対応付けは PC 側（下記 4.） | 「millis と GPS UTC の組み合わせ」の推定どおり（単位は ms でなく us） |
| K-Line / ECU 関連コード | **なし**（`kline`、`l9637`、`ecu` に該当する記述はスケッチ中に存在しない）。当時の方針は「あっても触らない」。2026-11-16 から、市販のアダプター越しの読み出しに限って認める（[analysis_policy.md](analysis_policy.md) 1.3） | — |

## 2. ファイル構成と列（9 本すべて同じ）

全ファイルがカンマ区切り・ヘッダー 1 行・UTF-8（`memo.txt`/`readme.txt` も UTF-8）。GPS と加速度は **別ファイル**。

### 2.1 `accel.csv`（実測 約398.5Hz）

| 列 | 型 | 内容 | 実測 |
|---|---|---|---|
| `n` | int | サンプル連番（0 から） | 9 本とも飛びなし（`diff(n)==1` が 100%） |
| `t_us` | int64 | サンプル時刻（起動からの us、PLL 推定） | 単調増加・重複 0。間隔 2,458〜2,592 us、中央値 2,499〜2,515 us |
| `ax_g`,`ay_g`,`az_g` | float | 加速度、**単位 g、重力込み**、センサー基板の軸のまま | 0.0039 g 刻み。静止時の合成加速度の中央値 0.945〜0.965 g（1 g より約 4〜5% 小さい＝ADXL345 のオフセット／感度の個体差。相対的な振動の評価には影響しない） |

### 2.2 `gps.csv`（1Hz、RMC 1 文 = 1 行）

| 列 | 型 | 内容 | 実測 |
|---|---|---|---|
| `t_rx_us` | int64 | RMC 文の先頭を受けた ESP 時刻 | 間隔中央値 1.000 s |
| `utc` | str `hhmmss.sss` | GPS 時刻 | 測位前は空。**測位していなくても時刻だけ入る行がある**（`status=V` かつ `utc` あり：ride_004 で 30 行、ride_005 で 76 行） |
| `date` | str `ddmmyy` | GPS 日付 | 同上 |
| `status` | `A`/`V` | RMC の有効フラグ | **有効判定はこの列で行う** |
| `fix` | int | GGA の fix 品質 | 0＝なし、1＝単独測位、**6＝推定（デッドレコニング）** が各走行 1〜3 行ある（fix 喪失直前・復帰直後）。`status=A` でも `fix=6` の行が存在する |
| `sats` | int | 使用衛星数 | 有効行で 3〜18 |
| `hdop` | float | 水平精度指標 | 有効行で 0.8〜9.9。未測位は 25.5 |
| `lat`,`lon` | float | 十進の度 | `status=V` では空。`status=A` で欠損・0 はなし |
| `speed_kmh` | float | RMC の対地速度（knot×1.852 をファーム側で変換済み） | 停止中でも 0〜4 km/h 程度出る |
| `course_deg` | float | 進行方向 | 未測位時は空。有効行では停止中も前の値が残る |

### 2.3 `events.csv`（`t_us,type,detail`）

9 本に出た type は `boot`、`gps_valid`、`gps_lost` のみ。`fifo_overrun`・`ring_drop`・`sd_write_error`・`time_resync`・`adxl_retry`・`sd_retry` は **0 件**。

### 2.4 `status.csv`（10 秒ごと）

`t_us,samples,rate_hz,ring_drops,fifo_overruns,i2c_errors,sd_write_errors,bytes,gps_status,gps_sats,period_us,dt_min_us,dt_max_us,pll_err_max_us,time_resyncs`。9 本とも欠け・エラー系の累計は全部 0。`pll_err_max_us` 最大 3,938 us（ride_005）。

### 2.5 `meta.json`

9 本同一：`spec="データ仕様.md v2"`、`firmware="CT125_LOGGER_V2.1"`、`accel={odr_hz:400, range_g:16, lsb_g:0.0039, unit:"g"}`、`gps={baud:9600, pps_pin:-1}`、`mounting="未記入"`。

## 3. 9 本の棚卸し

> **2026-11-09**：この 9 本はデバイス API から上げ直し、走行 ID がサーバーの付ける `ride_<日時>` に変わった（#15）。この文書の `ride_004` などは「元の名前」で、走行の台帳と画面にも元の名前として残っている。

| 元の名前 | 走行 ID（2026-11-09 から） | 分類 |
|---|---|---|
| ride_001 | ride_20261109_030057 | 停車 |
| ride_002 | ride_20261109_030100 | 停車 |
| ride_003 | ride_20261109_030103 | 停車 |
| ride_004 | ride_20261109_030109 | 実走 |
| ride_005 | ride_20261109_030119 | 実走 |
| ride_006 | ride_20261109_030126 | 机上（画面に出さない） |
| ride_007 | ride_20261109_030139 | 実走（GPS なし） |
| ride_008 | ride_20261109_030155 | 実走（GPS なし） |
| ride_009 | ride_20261109_030206 | 実走（GPS なし） |

| ride | 内容（memo/readme・推定） | 記録時間 | accel 行数 | 実測 fs [Hz] | GPS 行 | `gps_fix_ratio` | 開始時刻（JST、GPS から） | 用途 |
|---|---|---|---|---|---|---|---|---|
| ride_001 | アイドリング（サイドスタンド、傾き） | 2.0 分 | 48,004 | 399.1 | 120 | 0.70 | 11/02 13:35:25 | 試験。静止・アイドリングの基準 |
| ride_002 | アイドリング（同上） | 2.3 分 | 56,004 | 399.0 | 140 | 0.89 | 13:42:09 | 試験 |
| ride_003 | センタースタンドを外して発進（傾きの変化あり） | 1.5 分 | 35,200 | 398.8 | 88 | 0.98 | 13:48:52 | 試験。最高 12.6 km/h |
| **ride_004** | **短い往復の往路** | 13.9 分 | 332,408 | 398.2 | 834 | **0.95** | 14:03:38 | 主データ（地図・タイムライン・モデル） |
| **ride_005** | **ride_004 の復路** | 15.3 分 | 364,344 | 397.5 | 916 | **0.90** | 14:52:58 | 主データ |
| ride_006 | 不明（短い。GPS なし） | 1.7 分 | 39,600 | 398.5 | 99 | **0.00** | 不明 | 振幅が小さく、ほぼ静止・アイドリングの可能性 |
| **ride_007** | 郊外走行 | 37.4 分 | 895,204 | 399.0 | 2,244 | **0.00** | 不明 | GPS なし走行。振動特徴量の学習、欠損時フォールバックの検証 |
| ride_008 | 不明（GPS なし。取り付け姿勢が ride_007 までと違う） | 6.9 分 | 165,200 | 398.3 | 415 | **0.00** | 不明 | GPS なし |
| **ride_009** | 郊外走行（同 2 本目） | 31.1 分 | 746,312 | 400.2 | 1,865 | **0.00** | 不明 | GPS なし走行 |

- `gps_fix_ratio` は `status=A` の行数 ÷ 全行数。ride_001〜005 の無効分は主に起動直後の測位待ち（初回 fix まで 4〜38 秒）。
- 有効行の座標は（有効行がある 5 本とも）記録した地域の範囲に収まる（範囲外の点なし）。ride_004/005 の軌跡の広がりは約 2 km × 2 km。1 秒で 50 m 以上飛ぶ点は ride_004 の 2 点のみ（下記 5.2 の誤測位区間）。
- ride_006〜009 は **先頭から最後まで `sats=0`、`utc` も空**（時刻すら受信できていない）。ride_001〜005 が 4〜38 秒で測位できていることと合わせると、コールドスタート直後の未捕捉ではなく、受信そのものができていない（アンテナの遮蔽、または GPS TX 線の接触不良。机上の試験でも GPS の線の接触の緩さが見つかっている）可能性が高い。

## 4. 時刻の基準と同期

- 全列の時計は `t_us`。**走行内の相対時間** `t_rel = (t_us − t_us[0]) / 1e6` [s] は全走行で使える。
- **絶対時刻（UTC→JST）** は GPS 有効行から `offset = median(utc_unix − t_rx_us/1e6)` を求め、`t_abs = t_us/1e6 + offset`（[data_spec_v2.md](data_spec_v2.md) 2.、`pipeline/tools/ride.py` と同じ方法）。有効行間の `offset` のばらつきは標準偏差 18〜56 ms、範囲 104〜274 ms（NMEA の送信遅れ）。1 秒窓の解析には十分、サブ秒精度が要るなら PPS が必要（今回は不要）。
- GPS なし走行（ride_006〜009）は `t_abs` を **NaN** にする（analysis_policy.md 3.）。

## 5. データの品質

### 5.1 加速度

- 欠け・重複・エラー：**なし**（`n` 連番、`events.csv`・`status.csv` ともに 0）。ファイル分割もなし（1 走行 1 ファイル）。
- 値域：走行中の合成加速度の 99 パーセンタイルは ride_004 で 3.3 g、ride_007 で 6.3 g、ride_009 で 7.2 g。最大は ride_007 で 18.6 g（合成）。
- **振り切れ**：ADXL345 の FULL_RES ±16g の上限は約 ±15.97 g。`|ax| ≥ 15.9 g` は ride_007 で 1 サンプル、`|ax| ≥ 15 g` は 25 サンプル（X 軸のみ）。他軸・他走行は 0。つまり郊外走行では X 軸が上限に近づくことがある → 前処理で `is_clipped` フラグ（しきい値 15.9 g）を付ける。
- 重力の向き（静止 10 秒の平均）：ride_001〜007 は `(ax, ay, az) ≈ (0.1〜0.23, 0.83〜0.86, −0.40〜−0.42)`、ride_008/009 は `(0.10〜0.13, 0.96〜0.98, −0.19〜−0.24)`。**Y 軸がほぼ鉛直**、ride_008 以降は置き方が変わっている。軸と車体の向きの対応は [knowledge_preprocessing.md](knowledge_preprocessing.md) 4.

### 5.2 GPS

- 更新周期 1 Hz、`status=A` 時の `lat`/`lon` 欠損・0 はなし。
- **ride_004 14:16:30〜14:16:55（t_rel 773〜798 s）**：衛星 3〜6、HDOP 6.3〜9.7 のまま速度が 29→101 km/h に単調に増え、その直後 `gps_lost`（3 秒）。CT125 の走り方として不自然で、低品質測位による誤りとして扱う。この区間の速度・座標は使わない。
- **ride_005 14:55:23〜24**：衛星 3、HDOP 3.8 で 50→55 km/h、直後に 61 秒の `gps_lost`（14:55:25〜14:56:25）。復帰直後は `fix=6`。同じく除外候補。
- **ride_005 15:02:19〜15:02:54**：衛星 4〜6、HDOP 9.0〜9.9 が 36 秒続く（速度 21〜35 km/h は自然だが精度は低い）。
- 停止中の速度は 0〜4 km/h 程度出る → **5 km/h 未満は停止扱い**。

## 6. 特徴量計算に使う列・捨てる列

| ファイル | 使う | 使い方 | 捨てる・使わない |
|---|---|---|---|
| `accel.csv` | `t_us`, `ax_g`, `ay_g`, `az_g` | 1 秒窓（約 398 サンプル）で合成加速度を計算、窓内平均を引いて重力除去。fs は走行ごとに実測値（`(len−1)/(t_us[-1]−t_us[0])`）を使う。帯域特徴量（analysis_policy.md 2.4）は fs≈398 Hz ≥ 100 Hz なので **実装する**（ナイキスト約 199 Hz） | `n`（欠け検知にだけ使う） |
| `gps.csv` | `t_rx_us`, `utc`, `date`, `status`, `sats`, `hdop`, `lat`, `lon`, `speed_kmh` | `status=="A"` の行だけ使う。`t_rx_us`＋`utc`/`date` で offset を求める。速度は RMC の `speed_kmh` をそのまま使い（haversine は補助）、3 点移動中央値で平滑化。**品質フィルタ：`sats ≤ 4` または `hdop > 5` の行は無効化**（上記 5.2 の誤測位を落とすため。`pipeline/config/default.yaml` に置く） | `fix`（`status` で代替。6 は記録だけ残す）、`course_deg`（今回未使用） |
| `events.csv` | `gps_valid`/`gps_lost` | GPS 欠損区間の確認 | — |
| `status.csv` | — | 点検のみ（特徴量には使わない） | 全列 |
| `meta.json` | `firmware`, `accel.range_g`, `accel.lsb_g` | 記録条件の確認、クリップしきい値 | — |

### 前処理の判定値（`pipeline/config/default.yaml`）

| 名前 | 値 | 根拠 |
|---|---|---|
| `window_sec` | 1.0 | analysis_policy.md 2.1 |
| `clip_g` | 15.9 | FULL_RES ±16g の上限 15.97 g の手前 |
| `gps.min_sats` / `gps.max_hdop` | 5 / 5.0 | 5.2 の誤測位区間（sats 3〜4、HDOP 9.7）を除外、通常区間（sats ≥ 7、HDOP ≤ 2）は残る |
| `gps.max_jump_mps` | 50 | 時速 180 km 相当（analysis_policy.md 3.） |
| `gps.max_gap_sec` | 5 | 補間しない fix 間隔（analysis_policy.md 3.） |
| `stop_speed_kmh` | 5 | 停止中の見かけの速度 0〜4 km/h |
| `edge_sec` | 60 | 停車・取り回しの揺れを除く（analysis_policy.md 3.） |

## 7. 前処理の出力 `windows.parquet`（1 行 = 1 秒窓）

置き場所は作業用のバケットの `runs/<run_id>/rides/<ride_id>/windows.parquet`（[data_flow_design.md](data_flow_design.md) 4.）。

| 列 | 内容 |
|---|---|
| `ride_id`, `win` | 走行 ID、窓番号（0 から） |
| `t_rel`, `t_start` | 窓の中心・開始の相対秒 |
| `t_abs` | JST（tz 付き）。GPS なし走行は NaT |
| `lat`, `lon`, `speed_kmh`, `has_gps` | 有効 fix を窓中心に線形補間（fix 間隔が 5 秒超なら `has_gps=False`、座標・速度は NaN）。速度は RMC の値を 3 点移動中央値で平滑化 |
| `is_edge` | 先頭・末尾 60 秒 |
| `is_clipped`, `n_clipped` | 窓内に 15.9 g 以上のサンプルがあるか・その数 |
| `n_samples` | 窓内サンプル数（約 398） |
| `rms`, `log_rms`, `p2p`, `std`, `crest`, `jerk_rms` | analysis_policy.md 2.2。重力除去後の合成加速度で計算 |
| `band_1_5`, `band_5_15`, `band_15_40` | 帯域エネルギー比（3 軸の平均除去後の FFT パワーを足して正規化。合計 1） |
| `has_ecu` | ECU の回転数が入った窓（前の値で埋めた窓を含む）。ECU の無い走行・途切れた区間は False（#130。analysis_policy.md 2.5） |
| `ecu_rpm_mean`, `ecu_rpm_min`, `ecu_rpm_max` | ECU の回転数（rpm）の窓の中の平均・最小・最大。窓に値が無ければ 2 秒以内の前の値 |
| `ecu_throttle_pct`, `ecu_load_pct`, `ecu_map_kpa`, `ecu_timing_deg` | スロットル開度（%）・負荷（%）・吸気圧（kPa）・点火時期（度）の窓の中の平均。無ければ 3 秒以内の前の値 |
| `ecu_oil_temp_c`, `ecu_intake_temp_c`, `ecu_volt_v` | 油温（℃）・吸気温（℃）・ECU の電圧（V）。無ければ 15 秒以内の前の値 |

## 8. 点数付けの出力 `scored.parquet`

置き場所は `windows.parquet` と同じ `runs/<run_id>/rides/<ride_id>/`。`windows.parquet` の全列＋次の列。

| 列 | 内容 |
|---|---|
| `is_stopped` | `has_gps` かつ `speed_kmh < stop_speed_kmh`（5 km/h） |
| `z_speed` | 速度ビン（5 km/h）ごとの `log_rms` の中央値・MAD からの逸脱 `(log_rms − 中央値)/(1.4826×MAD)`。速度がない窓は NaN |
| `is_anomaly_z` | `z_speed > z_threshold`（3.0）かつ走行中 |
| `score_if` | Isolation Forest（振動特徴量 8 列＋`speed_kmh`。#81）の `decision_function` の符号反転。大きいほど異常。速度がない窓は NaN（#81 より前の版は振動特徴量 8 列だけで、全窓に付く） |
| `is_anomaly_if` | IF の外れ（contamination 3%）。判定には使わない |
| `is_anomaly_sif` | `score_if >` しきい値（学習に使った窓の `score_if` の `anomaly_quantile` 分位点。model.json の `forest.threshold`）かつ `z_speed > 0`（その速度でのふだんより振動が大きい側）かつ走行中 |

モデルは作業用のバケットの `models/<version>/baseline.json`（ビンごとの n・中央値・MAD・借用元ビン）と `isolation_forest.skops`（[data_flow_design.md](data_flow_design.md) 10.）。
