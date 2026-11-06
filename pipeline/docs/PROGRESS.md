# 進捗メモ

## フェーズ 0（2026-11-06）リポジトリ整備とデータ棚卸し

- できたこと：リポジトリ初期化（uv、Python 3.12、pyproject）、スケッチと SD 記録 9 本を `firmware/`・`data/raw/` にコピー、`docs/data_schema.md`（列・単位・fs 約398.5Hz・時刻基準・GPS 有効割合・使う列／捨てる列・フェーズ 1 の判定値）、`notebooks/01_inspect.ipynb`（実行済み、座標の実値は出力しない）、`docs/QUESTIONS.md`（3.4 の 9 項目に回答、質問 8-a/8-b/9〜13 を本人へ）、`docs/DEV_PLAN.md` に「実測」を追記。
- 分かったこと：9 本とも欠け・エラーなし。歯医者往復は ride_004（往路、fix 率 0.95）＋ ride_005（復路、0.90）の 2 本、郊外走行は ride_007・ride_009 で GPS は先頭から衛星 0（受信自体の問題が濃厚）。ride_004 の 100 km/h 区間と ride_005 の 55 km/h 区間は低品質測位で除外。ride_007 で X 軸が 15.9 g に 1 回到達。
- できなかったこと：自宅座標（質問 9）・センサー軸の向き（質問 10）・ride_006〜009 の内容（質問 8-b）は本人待ち。
- 次にやること：フェーズ 1（`src/ct125/{io,clean,gps,features,cli}.py`、`config/default.yaml`、`tests/`、`02_features.ipynb`）。自宅マスクは座標が届くまで `config/local.yaml` 不在なら全窓 `is_private=False` で進め、届いたら再実行。

## フェーズ 1（2026-11-06）ローカル解析パイプライン

- できたこと：`src/ct125/{config,io,clean,gps,features,cli}.py`、`python -m ct125 process --all` で 9 本すべて `data/processed/<ride>/windows.parquet`（計画書 9.3 の列＋帯域比 3 列＋`is_clipped`）と `data/interim/<ride>/{accel,gps}.parquet` を出力。`tests/` 10 件通過。`notebooks/02_features.ipynb` 実行済み。
- 確認したこと（完了条件）：歯医者往復は `has_gps` 0.92（ride_004）／0.87（ride_005）、GPS なし 4 本は全窓 `has_gps=False`・`t_abs` なし。速度と `log_rms` のスピアマン相関は 0.74／0.65（走行中のみ 0.39／0.37）で正の傾向あり。
- 計画書からの変更：帯域比の FFT は合成加速度でなく 3 軸別（整流で周波数が 2 倍に写るのを避ける）。GPS に「RMC 速度と位置移動の速度の不整合（25 km/h 超）」の無効化を追加（ride_004 で 19 行、ride_005 で 9 行が落ちる）。
- 分かったこと：ride_004 14:15:30〜48 の「98 km/h」区間は GPS 品質は良いが振動 RMS が 0.1〜0.5 g（45〜60 km/h の中央値 1.6 g より小さい）で、速度解の誤りが疑われる → `QUESTIONS.md` 11-b で確認待ち。確認できれば `gps.max_speed_kmh` で除外。
- できなかったこと・次：自宅マスクは `config/local.yaml` 待ち（置けば `process --all` の再実行だけ）。次はフェーズ 2（`model.py`：速度補正ベースライン＋Isolation Forest、`03_model.ipynb`、9.5 の妥当性チェック）。
