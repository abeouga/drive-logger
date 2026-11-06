# CT125_LOGGER_V2（フェーズ1：加速度＋GPS を microSD に記録）

ESP32 の電源を入れると自動で記録を始め、電源を切ると終わります。プログラムは ESP32 の中に入っているので、PC は要りません（USBバッテリー給電）。
記録の形は [データ仕様.md](../../データ仕様.md)（v2）に合わせています。

> 2026-11-02 に机上（ブレッドボード版 CT125-BB-R3、PC の USB 給電）で動作を確認しました。
> **バッテリーだけでの動作と、実車での走行記録はまだです。**

## 配線（実機で確認済み）

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
  accel.csv     n, t_us, ax_g, ay_g, az_g          （400Hz）
  gps.csv       t_rx_us, utc, date, status, fix, sats, hdop, lat, lon, speed_kmh, course_deg（1Hz）
  events.csv    t_us, type, detail                  （起動・再試行・あふれ・GPS 有効/無効）
  status.csv    10秒ごとの件数・実測周波数・取りこぼし数
```

- すべての時刻は ESP の時計 `t_us`（起動からのマイクロ秒）。GPS の UTC との対応は `gps.csv` の `t_rx_us`（RMC 文を受け取った時刻）と `utc` で取る。詳しくはデータ仕様.md 第2章。
- 加速度の単位は g。±16g、分解能 3.9mg。軸はセンサー基板の軸のまま。
- データ量は約15KB/秒（1時間で約55MB）。

## LED の見方（PC なしで動かすとき）

| LED | 意味 |
|---|---|
| 1秒に1回ゆっくり点滅 | 記録中・GPS 有効 |
| 短く2回ずつ点滅 | 記録中・GPS まだ（測位待ち） |
| 速い点滅（1秒に5回）が続く | **記録できていない**（SD か ADXL345 が NG） |
| 点かない | 電源が来ていない／LED が IO2 にない |

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
python tools/check_session.py E:/sessions
```

（`E:` はカードリーダーのドライブ。`tools/check_session.py` はこのリポジトリの最上位にある）
記録時間・実測周波数・サンプルの飛び・GPS の有効率・UTC の開始時刻・t_us と UTC のずれのばらつきを表示する。

## 書き込み方

```bash
"D:/ESP32/tools/arduino-cli/arduino-cli.exe" compile --config-file D:/ESP32/arduino-cli.yaml --fqbn "esp32:esp32:esp32:FlashMode=dio,FlashFreq=40,FlashSize=4M" --output-dir build .
```

```bash
"D:/ESP32/arduino-data/packages/esp32/tools/esptool_py/5.3.1/esptool.exe" --chip esp32 --port COM6 --baud 230400 write-flash 0x1000 build/ct125_logger.ino.bootloader.bin 0x8000 build/ct125_logger.ino.partitions.bin 0x10000 build/ct125_logger.ino.bin
```

元のプログラム（SD_READER_V1）は `../backup/before-check-4MB.bin`（4MB全体、実機と照合済み）。ソースは見つかっていない。

## まだやっていないこと

- バッテリーだけでの動作確認（手順は下）
- 実車での走行記録、振動の大きさ（±16g で足りるか）、周波数（400Hz で足りるか）
- センサーの軸と車体の向きの対応づけ
- GPS の PPS による UTC との精密な同期

## バッテリー単体テストの手順

1. ESP32 の USB を PC から抜く。
2. cheero のバッテリーに USB ケーブルでつなぐ（給電のみ）。
3. LED を見る：1秒に1回のゆっくり点滅になれば、記録中・GPS 有効。
4. 数分置いておく（できれば窓際か屋外で。途中で軽く揺らすと加速度の変化が見える）。
5. バッテリーから USB を抜いて電源を切る。
6. SD カードを抜いて PC のカードリーダーに挿し、`check_session.py` を実行する。
   （または ESP32 を PC につなぎ直すと、起動時のシリアル出力に前回のファイルの大きさが出る）
