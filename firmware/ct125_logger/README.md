# CT125_LOGGER_V3（加速度＋GPS を microSD に記録し、走行後に Wi-Fi で S3 へ送る）

ESP32 の電源を入れると自動で記録を始めます。プログラムは ESP32 の中に入っているので、PC は要りません（USBバッテリー給電）。
記録の形は [データ仕様 v2](../../docs/data_spec_v2.md)に合わせています（V3 でも同じ）。ファイルと列の正式な定義は [contracts/sd/](../../contracts/sd/)、送信の手順は [contracts/upload/](../../contracts/upload/)（CI がこのソースの定数と突き合わせる）。

**V3（2026-11-08）で足したこと**：走行後、止まって静か（エンジン停止）が 2 分続くか、BOOT ボタンを 2 秒押すと、
記録を閉じて Wi-Fi で S3 に送ります。そこから AWS の自動処理が動き、https://drive.herdio-system.com/ に出ます。
設計は [docs/device_upload_design.md](../../docs/device_upload_design.md)。電源を切れば今までどおり記録は終わります（送るのは次に止まったとき）。

> 記録は 2026-11-02 に机上（ブレッドボード版 CT125-BB-R3）で確認。V3 は 2026-11-08 に机上で、記録（399Hz・取りこぼし 0）と、
> **Wi-Fi で S3 へ送り、AWS の自動処理を経て公開一覧に載るまで**を確認（4.3MB を約 33 秒）。現在は V3.5。
> V3.2（2026-11-09）は、走行メモ `notes.md` を送るようにし、止まっているとみなす速さを 3 → 5 km/h にした（pipeline とそろえた）。
> V3.3（2026-11-09）は、送る走行の判定を meta.json の文字列の完全一致から JSON の値の読み取りに変えた（`json_lite.h`。コロンの前後の空白を許し、版の数で比べる。PC で動くテストは `firmware/tests/host/`）。**V3.2・V3.3 はコンパイルと PC のテストだけ確かめた。実機にはまだ書き込んでいない。**
> V3.4（2026-11-15）は、走行中に SD への書き込みが 1 度失敗すると、その CSV（accel.csv など）がその後ずっと書かれなかった不具合を直した。FatFs はファイルごとにエラーを覚えて以後の書き込みを断るので、書けなかったら閉じて追記で開き直し、切れた行の次の行の頭から書き続ける（`sd_write_recovery.h`）。書けなくなったとき・開き直したときを events.csv に `sd_write_error`・`sd_reopen` で残す。**コンパイルと PC のテストだけ確かめた。**
> V3.5（2026-11-15）は、加速度の ODR を 400 → 800 Hz にした（I2C 400 kHz のまま、`BW_RATE=0x0D`）。見える周波数が約 200 → 約 400 Hz に広がる。meta.json の `odr_hz` が 800 になり、accel.csv は 1 時間で約 115 MB（2 倍）。**コンパイルと PC のテストだけ確かめた。**
> 2026-11-10、1 つだった `ct125_logger.ino` を役割ごとのファイルに分けた（#27。関数の中身・定数・CSV と meta.json の書き出しは変えていないので、版は V3.3 のまま）。分けた後の版は、コンパイルだけ確かめた。
> **バッテリーでの「静か 2 分」からの自動送信と、実車での確認はまだです。**

| ファイル | 中身 |
|---|---|
| `ct125_logger.ino` | 起動（setup）と、状態の切り替え（記録中 → 送信 → 待機）。待機からの起き上がり（再起動） |
| `logger_constants.h` | 版の名前（`FW_VERSION`）・配線・記録の周期・送信のきっかけのしきい値 |
| `logger_state.cpp/.h` | 動作の状態と、タスクをまたぐ値（件数・止める合図・リングバッファ） |
| `event_log.cpp/.h` | events.csv への出来事の書き込み |
| `adxl345.cpp/.h` | ADXL345 のレジスタ、I2C の線の解放、初期化 |
| `accel_sampler.cpp/.h` | 加速度のタスク（時刻の補正 PLL と 800Hz のサンプリング）→ accel.csv |
| `nmea.cpp/.h`・`gps_task.cpp/.h` | NMEA の読み取りと GPS のタスク → gps.csv |
| `sd_session.cpp/.h` | 走行のフォルダー、meta.json、CSV の見出しと書き出し、status.csv |
| `sd_write_recovery.h` | SD に書けなくなった CSV の開き直し（行の頭から書き続ける）。SD に頼らないので PC でテストできる（`../tests/host/`） |
| `motion.cpp/.h` | 静か・動き出しの判定（送信のきっかけ・送信の中断・待機からの起き上がり） |
| `led.cpp/.h`・`boot_button.cpp/.h`・`serial_commands.cpp/.h` | LED、BOOT ボタン、シリアルのコマンド（`UPLOAD`・`LOG`・`CFG`） |
| `uploader.cpp/.h` | Wi-Fi・HTTPS・送信の手順（PC から送る `python -m ct125 upload-sd` と同じ手順） |
| `json_lite.h` | 小さな JSON の読み取り（応答・meta.json）と、送る走行の判定。Arduino の String だけに頼るので PC でテストできる（`../tests/host/`） |
| `config_store.cpp/.h` | Wi-Fi と機器トークンの保存（NVS）と、シリアルからの設定 |
| `root_ca.h` | HTTPS で信頼するルート証明書（Amazon Root CA 1 など） |

## 配線（実機で確認済み）

配線図は [docs/hardware/配線図/配線図.png](../../docs/hardware/配線図/配線図.png)。

| 部品 | ESP32 |
|---|---|
| ADXL345（GY-291） | SDA=IO21、SCL=IO22、CS=3V3、SDO=GND（I2C 0x53） |
| GPS（ATGM336H） | GPS TX → IO32、GPS RX ← IO33、9600bps。PPS は未接続 |
| microSD（秋月105488） | CS=IO5、SCK=IO18、MISO=IO19、MOSI=IO23、3.3V |
| LED | IO2（ボード上の LED と仮定。点くかは要確認） |

## SDカードに書かれるもの

```
/sessions/ride_NNN/     電源を入れるたびに新しく作る（001 から順番）
  meta.json     版・設定・単位・軸の説明
  accel.csv     n, t_us, ax_g, ay_g, az_g          （800Hz。V3.4 までは 400Hz）
  gps.csv       t_rx_us, utc, date, status, fix, sats, hdop, lat, lon, speed_kmh, course_deg（1Hz）
  events.csv    t_us, type, detail                  （起動・再試行・あふれ・GPS 有効/無効）
  status.csv    10秒ごとの件数・実測周波数・取りこぼし数
  notes.md      走行メモ（PC で後から入れる。古い名前の memo.txt も送る）
  upload_state.json・uploaded.json   送信の途中・送り終えた印（V3）
/upload_log.csv         送信の記録（V3）
```

- すべての時刻は ESP の時計 `t_us`（起動からのマイクロ秒）。GPS の UTC との対応は `gps.csv` の `t_rx_us`（RMC 文を受け取った時刻）と `utc` で取る。詳しくは [データ仕様 v2](../../docs/data_spec_v2.md) の 2 章。
- 加速度の単位は g。±16g、分解能 3.9mg。軸はセンサー基板の軸のまま。
- データ量は約15KB/秒（1時間で約55MB）。

## LED の見方（PC なしで動かすとき）

| LED | 意味 |
|---|---|
| 1秒に1回ゆっくり点滅 | 記録中・GPS 有効 |
| 短く2回ずつ点滅 | 記録中・GPS まだ（測位待ち） |
| 速い点滅（1秒に5回）が続く | **記録できていない**（SD か ADXL345 が NG） |
| 1秒ついて1秒消える | 送信中（V3） |
| つきっぱなし | 送信が終わった、または送るものが無い（V3）。動き出すと再起動して次の記録を始める |
| 短く3回ずつ点滅 | 送れなかった（Wi-Fi が見つからない・設定が無い・失敗。V3）。BOOT ボタン 2 秒でやり直す。SD の `/upload_log.csv` に理由 |
| 点かない | 電源が来ていない／LED が IO2 にない |

## Wi-Fi で送る（V3）

- **送るきっかけ**：走行で一度動いた後、静か（1 秒ごとの振動のばらつき 0.02g 未満、GPS 速度 5km/h 未満）が 2 分続く。または BOOT ボタンを 2 秒押す。シリアルに `UPLOAD` と送っても同じ
- **送るもの**：`/sessions/` のうち、V3 以降で記録した（meta.json の `firmware` の値を JSON として読み、版の上の数が 3 以上）・30 秒以上・`uploaded.json` が無い走行（V2 までの走行は送らない）
- **送り終わったら**：その走行に `uploaded.json`（サーバーが付けた走行名）を書く。途中で切れたら `upload_state.json` の走行名で続きから
- **記録が優先**：自動で始めた送信は、走り出したら（動きが約 1 秒続いたら）ファイルの合間でやめる。待機中に 3 秒続けて動いたら再起動して記録を始める
- **手で始めた送信はやめない**：BOOT ボタン・シリアルの `UPLOAD` で始めた送信は、揺れてもやめない（V3.1。V3.0 ではボタンを押す手の揺れで最初のファイルの前に止まった）
- **送信の記録**：SD の `/upload_log.csv`。シリアルに `LOG` と送ると最後の約 40 行を出す（SD を抜かずに理由が見られる）
- **秘密の置き場所**：Wi-Fi のパスワードと機器トークンは ESP32 の内部フラッシュ（NVS）だけ。ソースにも SD にも書かない

最初の設定（1 回だけ。パスワードは利用者が入力する）。機器トークンは `pipeline/` で作る：

```bash
.venv/Scripts/python.exe -m ct125 register-device --id d01 --token-file config/d01.token
```

ESP32 に書き込む（`firmware/` で。トークンのファイルは上で作ったもの）：

```powershell
./scripts/provision-device.ps1 -Port <ポート> -Ssid <2.4GHz の SSID> -DeviceId d01 -TokenFile ../pipeline/config/d01.token
```

ESP32 は 5GHz の Wi-Fi に対応していないので、5GHz の SSID は使えない。設定の確認はシリアルに `CFG STATUS`（値は出さず、入っているかどうかだけ出す）。

## 電源断への強さ

- 1秒ごとに SD へ確定（flush）。電源が突然切れても、失うのは最後の約1秒だけ。
- 記録中の強制リセット試験（V1 で14回）で、毎回それまでのファイルが残ることを確認済み。
- 起動時に I2C の線の解放、ADXL345・SD の再試行を行う。再試行したことは `events.csv` に残る。

## 机上での実測（V2、2026-11-02）

| 項目 | 結果 |
|---|---|
| 加速度の実測周波数 | 398.6Hz（設定400Hz） |
| 取りこぼし・FIFO のあふれ | 0・0 |
| GPS | 有効（A）、衛星15〜16機（屋内・窓際） |

## 記録を PC で確かめる

SD カードをカードリーダーで PC に読ませてから：

```bash
python pipeline/tools/check_session.py <SD の sessions フォルダー>
```

（リポジトリの直下から。`<SD の sessions フォルダー>` はカードリーダーに挿した SD の `/sessions`）
記録時間・実測周波数・サンプルの飛び・GPS の有効率・UTC の開始時刻・t_us と UTC のずれのばらつきを表示する。

## 書き込み方

```bash
arduino-cli compile --fqbn "esp32:esp32:esp32:FlashMode=dio,FlashFreq=40,FlashSize=4M" --output-dir build .
```

```bash
"<arduino-cli のデータのフォルダー>/packages/esp32/tools/esptool_py/5.3.1/esptool.exe" --chip esp32 --port <ポート> --baud 230400 write-flash 0x1000 build/ct125_logger.ino.bootloader.bin 0x8000 build/ct125_logger.ino.partitions.bin 0x10000 build/ct125_logger.ino.bin
```

（ポートは PC によって変わる。`arduino-cli board list` で確かめる）

## バッテリー単体テストの手順

1. ESP32 の USB を PC から抜く。
2. cheero のバッテリーに USB ケーブルでつなぐ（給電のみ）。
3. LED を見る：1秒に1回のゆっくり点滅になれば、記録中・GPS 有効。
4. 数分置いておく（できれば窓際か屋外で。途中で軽く揺らすと加速度の変化が見える）。
5. バッテリーから USB を抜いて電源を切る。
6. SD カードを抜いて PC のカードリーダーに挿し、`check_session.py` を実行する。
   （または ESP32 を PC につなぎ直すと、起動時のシリアル出力に前回のファイルの大きさが出る）
