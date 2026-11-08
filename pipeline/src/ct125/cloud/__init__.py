# -*- coding: utf-8 -*-
"""AWS 上で動かす処理（Lambda のコンテナ）。

S3 の raw/<走行>/ に upload_complete.json が置かれると、その走行を
前処理 → 学習済みモデルで点数付け → 画面用データの書き出し まで行い、S3 に上げる。
手動で {"action": "retrain"} を渡すと、全走行で学習し直して、全走行を書き出し直す。

| ファイル | 役割 |
|---|---|
| lambda_handler.py | 入口。イベントを読み、どの処理をするか決める |
| commands.py       | イベント → 命令（走行を処理する／学習し直す） |
| ride_pipeline.py  | 処理の流れ（前処理・点数付け・書き出し・アップロード） |
| workspace.py      | /tmp の作業フォルダーの置き方 |
| s3_store.py       | S3 とのやりとり |
| model_registry.py | 学習済みモデルの保存場所と「今使う版」 |
| rides_index.py    | rides.json の 1 件を差し替える（同時に書いても壊れないように） |
| settings.py       | 環境変数 |
"""
