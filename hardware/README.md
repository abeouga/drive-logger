# hardware：ロガーの回路

ESP32・ADXL345・GPS・microSD のつながり（回路）の正本を、KiCad の回路図で持つ。部品の置き場所や、車体への取り付け・収まりは、別に Blender のブレッドボードのモデルで見る。2 つは同じ端子の番号を使い、つながりが一致するかをスクリプトで照合する。

| 何を見るか | どこで | 置き場所 |
|---|---|---|
| どこと何がつながるか（回路の正本） | KiCad 10 の回路図 | [kicad/ct125_logger/](kicad/ct125_logger/) |
| 部品をどこに置き、線をどう通すか（3D） | Blender のブレッドボードのモデル（版 `CT125-BB-R6A` / `R6B`） | このリポジトリの外。配置と接続の元データは、モデルの `layout.py` |
| 2 つの端子の対応 | 対応表 | [kicad/blender_correspondence.json](kicad/blender_correspondence.json) |
| 2 つのつながりが同じか | 照合のスクリプト | [tools/check_blender_nets.py](tools/check_blender_nets.py) |
| 説明用の配線図（1 枚の絵） | — | [docs/hardware/配線図/](../docs/hardware/配線図/) |

## 回路図の中身

2026-11-02 に実機で動作を確かめた配線を描いた。ピンは firmware の `firmware/ct125_logger/logger_constants.h` の `PIN_*` と同じ。

| 部品（回路図の記号） | つなぎ方 |
|---|---|
| ESP32 開発ボード（Freenove・WROOM、U1） | 電源はモバイルバッテリーから USB で取る。+3V3 はボードの 3.3 V |
| ADXL345（GY-291、U2） | I2C：SDA=IO21、SCL=IO22。CS→3V3、SDO→GND でアドレス 0x53。INT1・INT2 は使わない |
| GPS（ATGM336H、U3） | UART 9600 bps：GPS の TX→IO32、IO33→GPS の RX。PPS は使わない |
| microSD（秋月 AE-MICRO-SD-DIP、J1） | SPI：CS=IO5、SCK=IO18、MISO=IO19、MOSI=IO23。3.3 V だけ。DAT2・CS・CMD・DAT0・DAT1 を 10 kΩ（R1〜R5）で引き上げる。0.1 µF・1 µF（C1・C2）を電源のそばに置く |

K-Line（ECU）の回路は作っていないので、回路図に入れていない。

ESP32・GY-291・GPS・microSD の記号は、KiCad の標準の部品集に無いので、[kicad/ct125_logger/ct125.kicad_sym](kicad/ct125_logger/ct125.kicad_sym) に作った（プロジェクトの `sym-lib-table` から読む）。抵抗・コンデンサ・電源の記号は標準の部品集（`Device`・`power`）のもの。

## Blender のモデルとの対応

- **ESP32 のピン番号**：回路図の U1 のピン番号 `R1`〜`R20`・`L1`〜`L20` は、Blender のモデルと配線表の「右列／左列の n 番目（USB 側から数える）」と同じ。ESP32 は裏返して置いているので、ピンの並びは表から見た図の鏡像になる。1 本ずつの照合は、実機でまだしていない
- **ボードの中のつながり**：ESP32 の同じ名前の 5V・3V3・GND のピンは、ボードの中でつながっている。Blender のモデルは全部をネットに入れ、回路図は線を挿していないピン（GND の L2・L14・L20 など）に未接続の印を付けている。照合では、ボードの中のつながりを足してから比べる
- **部品の名前**：Blender の `R_DAT2`・`R_DAT3`・`R_CMD`・`R_DAT0`・`R_DAT1` が回路図の `R1`〜`R5`、`C_0u1`・`C_1u` が `C1`・`C2`。ネットの名前の対応（`SD_MISO_DAT0`↔`SD_MISO` など）も対応表にある
- **比べないもの**：Blender のモデルにある K-Line の追加案（A・B）は比べない

## 確かめ方

回路図の規則の検査（ERC）：

```bash
kicad-cli sch erc --severity-all hardware/kicad/ct125_logger/ct125_logger.kicad_sch
```

Blender のモデルとつながりが同じか（Python の標準ライブラリだけで動く。kicad-cli は `--kicad-cli`・環境変数 `KICAD_CLI`・PATH の順に探す）：

```bash
python hardware/tools/check_blender_nets.py --layout <Blender のモデルの layout.py>
```

一致すれば「結果: すべて一致」と出て 0 で終わる。配線を変えるときは、回路図を先に直し、Blender のモデルの `layout.py` を合わせてから、この 2 つを通す。

CI では回さない（KiCad と Blender のモデルが CI に無いため）。
