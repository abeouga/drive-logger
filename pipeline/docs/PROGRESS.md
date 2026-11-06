# 進捗メモ

## フェーズ 0（2026-11-06）リポジトリ整備とデータ棚卸し

- できたこと：リポジトリ初期化（uv、Python 3.12、pyproject）、スケッチと SD 記録 9 本を `firmware/`・`data/raw/` にコピー、`docs/data_schema.md`（列・単位・fs 約398.5Hz・時刻基準・GPS 有効割合・使う列／捨てる列・フェーズ 1 の判定値）、`notebooks/01_inspect.ipynb`（実行済み、座標の実値は出力しない）、`docs/QUESTIONS.md`（3.4 の 9 項目に回答、質問 8-a/8-b/9〜13 を本人へ）、`docs/DEV_PLAN.md` に「実測」を追記。
- 分かったこと：9 本とも欠け・エラーなし。歯医者往復は ride_004（往路、fix 率 0.95）＋ ride_005（復路、0.90）の 2 本、郊外走行は ride_007・ride_009 で GPS は先頭から衛星 0（受信自体の問題が濃厚）。ride_004 の 100 km/h 区間と ride_005 の 55 km/h 区間は低品質測位で除外。ride_007 で X 軸が 15.9 g に 1 回到達。
- できなかったこと：自宅座標（質問 9）・センサー軸の向き（質問 10）・ride_006〜009 の内容（質問 8-b）は本人待ち。
- 次にやること：フェーズ 1（`src/ct125/{io,clean,gps,features,cli}.py`、`config/default.yaml`、`tests/`、`02_features.ipynb`）。自宅マスクは座標が届くまで `config/local.yaml` 不在なら全窓 `is_private=False` で進め、届いたら再実行。
