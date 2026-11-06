# CT125 走行データロガー 解析パイプライン

ハンターカブ CT125（JA55）に載せた ESP32 ロガー（ATGM336H GPS ＋ ADXL345 加速度 ＋ microSD）の走行記録を、
ローカル解析 → 地図・タイムライン可視化 → AWS（S3）保管・配信 へつなぐポートフォリオ。

- 計画：[docs/DEV_PLAN.md](docs/DEV_PLAN.md)（表現上の制約 4. と作業ルール 7. を全成果物に適用）
- データの実測スキーマ：[docs/data_schema.md](docs/data_schema.md)
- 未確定事項・質問：[docs/QUESTIONS.md](docs/QUESTIONS.md)
- 進捗：[docs/PROGRESS.md](docs/PROGRESS.md)

## 現在の状態（2026-11-06、フェーズ 0 完了）

- 2026-11-02 に実車で記録した 9 本（`data/raw/ride_001`〜`ride_009`、コミット対象外）を棚卸しし、列・単位・サンプリング周波数（約 398.5 Hz）・時刻基準・GPS 有効割合を確定した。
- 健康な車両の走行データのみ。故障データは含まれていないため、この先作る異常スコアは「速度で補正した正常時のベースラインからの逸脱」であり、故障の予測ではない。
- ECU / K-Line 接続はスコープ外（端子・電圧・プロトコルが未検証で期限内に安全に検証できないと判断）。GPS と振動の 2 系統でパイプラインを作る。

## セットアップ

```bash
uv venv --python 3.12
```

```bash
uv pip install -e ".[dev]"
```

ノートブックの実行：

```bash
.venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_inspect.ipynb
```

## 構成

計画書 6. のとおり（`src/ct125/` にパイプライン、`notebooks/` は確認用、`web/` は生成物、`data/raw/`・`config/local.yaml` はコミットしない）。
