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

## フェーズ 2（2026-11-06）モデル

- できたこと：`src/ct125/model.py`（速度 5 km/h ビンの中央値・MAD による `z_speed`、振動特徴量だけの Isolation Forest による `score_if`）、`python -m ct125 score` で 9 本に `scored.parquet`、`data/models/<日付>/{baseline.json,isolation_forest.pkl}`。`tests/test_model.py` 追加（計 13 件通過）。`notebooks/03_model.ipynb` 実行済み。**主スコアは `z_speed`**（既定どおり）。
- 9.5 妥当性チェックの結果：
  1. 速度との関係：**期待どおり**。5 km/h 以上でビン中央値が単調に近く上がる（log_rms −0.77 → +0.57 at 50〜55 km/h）。
  2. 往路・復路の一致：**確認できず**。20〜100 m のどのグリッドでも rms の Spearman ≈ 0（p > 0.3）。往路 233 マス中、復路と共通は 56 マスだけで、同じマスの速度も一致しない（対向車線・GPS 誤差・運転の違い・暫定固定）。
  3. 上位異常の目視：**走行中（≥5 km/h）に z>3 の窓はなし**（最大 z 2.06）。上位 10 窓は ride_004 14:05〜14:08（下表）。本人の心当たりは未確認。
- 設計上の判断：0〜5 km/h ビンはアイドリング窓が大半で MAD 0.057 と極端に小さく、発進・取り回しの窓がすべて z>3 になるため、`is_anomaly_z` は走行中の窓だけに立てる（`is_stopped` 列を追加）。z<−3 の 23 窓はすべて ride_004 14:15:40〜49 の「98 km/h」区間で、GPS 速度の誤りを振動側からも裏づける（QUESTIONS 11-b）。
- `score_if`（contamination 3%）は 172 窓で、うち 166 窓が郊外走行 ride_007/009（rms 中央値 5.2 g、全窓 0.74 g）。速度を使わないので「絶対的に振動が大きい窓」を拾い、`z_speed` との相関はほぼ 0。
- 次（フェーズ 3）：地図＋タイムラインの HTML。z>3 の窓がないので、マーカーはしきい値超えに加えて「z_speed 上位 N 窓」も描けるようにする（しきい値自体は下げない）。

### z_speed 上位 10 窓（走行中、is_edge 除く）— 本人に心当たりを聞く

| # | ride | JST | 速度 km/h | rms g | z_speed | score_if | 心当たり |
|---|---|---|---|---|---|---|---|
| 1 | ride_004 | 14:07:48 | 20.2 | 2.00 | 2.06 | −0.17 | （未確認） |
| 2 | ride_004 | 14:07:49 | 26.8 | 1.96 | 1.95 | −0.09 | （未確認） |
| 3 | ride_004 | 14:07:50 | 34.5 | 2.00 | 1.92 | −0.18 | （未確認） |
| 4 | ride_004 | 14:08:08 | 39.2 | 2.59 | 1.87 | −0.14 | （未確認） |
| 5 | ride_004 | 14:06:33 | 29.7 | 1.87 | 1.87 | −0.18 | （未確認） |
| 6 | ride_004 | 14:06:31 | 22.2 | 1.66 | 1.79 | −0.17 | （未確認） |
| 7 | ride_004 | 14:07:46 | 11.6 | 2.34 | 1.74 | −0.15 | （未確認） |
| 8 | ride_004 | 14:08:07 | 36.9 | 2.38 | 1.73 | −0.05 | （未確認） |
| 9 | ride_004 | 14:08:06 | 36.9 | 2.38 | 1.73 | −0.06 | （未確認） |
| 10 | ride_004 | 14:05:37 | 20.3 | 1.53 | 1.67 | −0.20 | （未確認） |

14:07:46〜50 と 14:08:06〜08 は 3 窓連続で高く、突発（1 窓）ではなく数十 m の区間（荒れた舗装・工事跡など）の可能性がある。

## フェーズ 3（2026-11-06）可視化と Web 出力

- できたこと：`src/ct125/viz.py`、`python -m ct125 render` で `web/index.html`（走行一覧）と `web/<ride_id>/index.html`（folium 地図＋Plotly タイムライン、1 ファイル）。地図の線は log_rms の 5 分位で 5 色、赤丸＝z>3、橙丸＝z_speed 上位 10 窓、is_private の窓は描かない。`tests/test_viz.py`（地図の判定ロジック）追加、計 16 件通過。
- 確認したこと：ride_004/005 は地図（線分 766 本、マーカー 10）＋タイムライン、ride_006〜009 は地図なし＋「GPS が捕捉できなかった」注意書き＋相対秒のタイムライン。一覧の 9 行中 4 行に「地図なし」。禁止表現なし。GPS なし走行のページはブラウザで表示を確認。地図ページは座標がタイルサーバーに送られるため、こちらではブラウザで開いていない（本人が確認する）。
- 未適用：`config/local.yaml` がないので自宅マスクは未適用。地図ページには赤の注意（公開・アップロード禁止）を出している。local.yaml を置いて `process --all` → `score` → `render` を再実行すればマスクされる。
- 次（フェーズ 4）：S3 へのアップロードと署名付き URL。**マスク適用後に行う**。リージョンは AWS Settings または `~/.aws/config` で確認してから。

## フェーズ 4（2026-11-06）AWS 最小構成（途中）

- できたこと：専用アカウントの CLI プロファイル `ct125-logger` を登録。`D:\ct125-logger-terraform` の Terraform で S3 バケット（東京、非公開・SSE-S3・HTTPS のみ・バージョニング・ACL 無効）を作成し、AWS CLI で設定を確認。`models/` をアップロードして書き込みを確認。`src/ct125/aws.py` と `docs/aws_setup.md`、`docs/architecture.md`。
- できなかったこと：`raw/`・`processed/`・`site/` のアップロードと署名付き URL の発行。自宅座標（`config/local.yaml` の `home`）待ち。マスク未適用の走行ページはコードが拒否する。
- 確認待ち：リージョンが本当に ap-northeast-1 か（AWS Settings で確認）。貼られたアクセスキーのローテーション（URL 発行の前に行う）。
- 次：home を書く → `process --all` → `score` → `render` → `upload` → スマホで `share` の URL を確認。
- バケットは当面残す（本人決定）。削除するかは後で決める。
- 追記（同日）：自宅座標を `config/local.yaml` に設定（コミットしない）。走行の出発・到着の fix は自宅から 4〜12 m で整合。マスク（半径 300 m）で ride_004 は 63 窓、ride_005 は 79 窓、ride_001〜003 は GPS のある窓すべてを地図から除外。生成した HTML の座標を全点検査し、自宅から 300 m 以内の点は 0（最も近い点 303 m）。`raw/`・`processed/`・`site/`・`models/` を S3 にアップロード（74 オブジェクト、約 112 MB）。
- 修正：署名付き URL が SigV2・共通エンドポイントで作られ 307 で開けなかったため、SigV4・リージョン付きエンドポイントに変更。1 時間の URL で ride_004 が HTTP 200、署名なし・HTTP は 403 を確認。
- 残り：スマホでの表示確認、見せる前に `share --expires-hours 72` で URL を発行（アクセスキーのローテーションはその前に）。走行ページの「← 走行一覧」リンクは S3 上では開けない（一覧ページは署名付き URL で別途渡す必要がある）。

## Web アプリ版 11/7 分（2026-11-06 実施）書き出し・雛形・走行一覧

- できたこと：`python -m ct125 export`（`web-app/src/data/` に rides.json と ride_<id>.json。自宅 300 m の窓は lat/lon を null）と `check-privacy`、`tests/test_export.py`（計 22 件通過）。`web-app/`（React 19・TypeScript・Vite 8・Tailwind 4、1 ファイルビルド）と走行一覧（9 枚のカード、スパークライン、ハッシュで走行ページへ）。
- 検査：書き出した JSON とビルド後の `dist/index.html`（1.1 MB）の座標 1,422 点に、自宅 300 m 以内は 0（最も近い点 303 m）。一覧はスマホ幅 375 px・明暗両方で崩れず、コンソールのエラーなし。
- 計画からの変更：書き出し先は `public/data` ではなく `src/data`（1 ファイルビルドに埋め込むため）。タイムラインは右軸の速度をやめ、横軸を共有する上下 2 段にする（2 軸グラフを避ける）。
- 要確認：ride_004 のカードの最高速度が 98 km/h（14:15 の区間。QUESTIONS 11-b）。実速度でなければ `gps.max_speed_kmh` を入れて process から再実行。
- 次（11/8 分）：走行ページの地図（MapLibre・OpenFreeMap）とタイムライン（ECharts）の連動、GPS なしの表示。

## Web アプリ版 11/8 分（2026-11-06 実施）走行ページ：地図とタイムラインの連動

- できたこと：地図（MapLibre GL 6・OpenFreeMap、明暗でスタイル切り替え）、タイムライン（ECharts 6、横軸共有の 3 段：rms 対数軸／速度／z_speed）、詳細パネル（見どころ一覧・選んだ 1 秒の値と帯域比）、GPS なしの説明カード。地図の線・グラフ・見どころ一覧のどこで選んでも 3 つが追従し、グラフの範囲選択で地図がその区間に寄る。
- 確認：ride_004 で一覧の 1 位（14:07:48）を選ぶと詳細・グラフの縦線・地図の輪が一致。ride_007 は地図の代わりにカード。スマホ幅 375 px で横スクロールなし。`dist/index.html`（3.4 MB、gzip 0.87 MB）の座標 1,422 点に自宅 300 m 以内は 0。禁止表現なし。
- 計画からの変更：地図の色は虹色（青→黄→赤）ではなく単色の 5 段階。z_speed は停止中を描かない（停止ビンの MAD が極小で ±20 超の針になるため）。地図は Ctrl＋ホイールで拡大（ページのスクロールを妨げない）。1 ファイル化のため MapLibre のワーカーは Blob URL で起動。
- 気づき：GPS なし走行の Isolation Forest 上位には「静かすぎる」窓も入る（ride_007 の 1 位は rms 0.03 g）。画面の説明に明記した。
- 次（11/9 分）：詳細パネルの生波形、スペクトログラムのタブ、スマホのタブ切り替え、About ページ。

## Web アプリ版 11/9 分と移行（2026-11-06 実施）

- できたこと：フロントを `D:\ct125-app`（別リポジトリ）に移した。dev は Vite のサーバーが S3 の `app/v1/`（または `cache/`）から読み、build は `cache/` を埋め込んだ 1 ファイル。11/9 分（スペクトログラムのタブ、詳細パネルの生波形、スマホのタブ切り替え、この分析について）もそちらで実装。こちらは `spectro.py`（スペクトログラム PNG・生波形の書き出し、テスト 4 件）と、`export --upload`・`upload --site-app`・`share --app` を追加。
- 確認：ct125-app の `dist/index.html`（4.3 MB）に自宅 300 m 以内の座標 0、バケット名・AWS の設定なし、禁止表現なし。dev サーバーはフォルダー外のファイル名を 400 で拒否。アイドリング中の強い周波数は 20〜26 Hz。
- 未実施（本人の確認待ち）：S3 の `app/v1/` と `site-app/index.html` へのアップロード。`web-app/` は 11/8 の状態のまま残している（削除するかは確認待ち）。
- 次：アップロード → `DATA_SOURCE=s3` で dev を確認 → 1 ファイルを `site-app/` に上げ、署名付き URL をスマホで確認。
- 追記（同日）：本人の了承を得て `export --upload` で S3 の `app/v1/` に 37 ファイル（約 1.8 MB）を上げた。ct125-app を `DATA_SOURCE=s3` にして読めることと、`pull-data.ps1` の同期を確認。`site-app/index.html` へのアップロードと `web-app/` の扱いは未決。
- 追記（同日）：本人の了承を得て `web-app/` を削除（コードは `D:/ct125-app` に移行済み、データは S3 の `app/v1/` と `export` で作り直せる）。

## 公開版：CloudFront＋Cognito＋データ API（2026-11-07 実施）

- できたこと：https://drive.herdio-system.com/ で公開（ログイン必須）。構成は CloudFront（`/*` → S3 `webapp/`、`/api/*` → API Gateway HTTP API）、API Gateway の JWT オーソライザー（Cognito）、Lambda のデータ API（`D:/ct125-app/api`、FastAPI＋Mangum、Python 3.13 arm64）。Terraform は `D:/ct125-logger-terraform`（追加 23・変更 1）。証明書は CloudFront 用に us-east-1、DNS は Cloudflare（`herdio-system.com`、2 つの CNAME はどちらもプロキシなし）。
- データの置き場所：`app/v1/datasets/shared/` に移した（`app/v1/` の 37 ファイルをコピー。元は残している）。`config/default.yaml` の `aws.app_prefix` も変更。ユーザーごとにデータを分ける入口は `api/src/ct125_api/services/dataset_resolver.py`（今は全員 shared）。
- ユーザー：Terraform（`cognito_users.tf`、値は `terraform.tfvars`、コミットしない）で admin と閲覧用のユーザーを作る。destroy しても apply で同じユーザー・パスワードに戻る。パスワードの決まりは本人の判断で緩めている（8 文字以上・英小文字と数字）。後で戻すこと。
- 確認：`/api/health` 200、トークンなし・不正トークンで `/api/me`・`/api/data/*` は 401。CloudFront 経由で `site/`・`raw/`・`app/v1/datasets/` は 403（webapp/ 以外は見えない）。HTTP は HTTPS へ 301、HSTS・nosniff・X-Frame-Options あり。Lambda を直接呼んで S3 から 9 走行と PNG（バイナリ）が返ることを確認。ログインボタンから Cognito の日本語のログイン画面（PKCE S256）へ移ることを確認。
- 本人の確認（同日）：公開版にログインできた。
- 計画からの変更：署名付き URL と 1 ファイル HTML の配布はやめ、CloudFront＋ログインにした。1 ファイル版は `npm run build:single` として残している。
- 次：B（S3 の raw/ に置くと Lambda が前処理 → 推論 → JSON 書き出しまでする）。

## B：AWS 上の自動処理（2026-11-07 実施）

- できたこと：S3 の `raw/<走行>/upload_complete.json` を合図に、Lambda（コンテナ `ct125-ride-pipeline`、Python 3.12・x86_64・3008 MB）が 前処理 → 学習済みモデルで点数付け（推論だけ）→ 画面用データの書き出し → 座標検査 → `processed/` と `app/v1/datasets/shared/` へ上げ、`rides.json` の 1 件を差し替える。手動の `{"action": "retrain"}` で全走行の学習し直し（新しい版を `models/<日時>/` に置いてから `models/current.json` を切り替える）。
- コードの整理：`process_ride`・`score_all` を `cli.py` から `processing.py` へ、`model.py` を `fit_models`（学習）と `apply_models`（推論）に分割、`export.py` に 1 走行ずつの `export_ride`、`io.read_memo`。AWS 用は `src/ct125/cloud/`（commands・ride_pipeline・s3_store・model_registry・rides_index・private_points・workspace・settings・lambda_handler）。テスト 43 件（追加 17）。
- 自宅座標：`python -m ct125 sync-private-points` で座標だけを SSM の SecureString `/ct125/private-points` に上げた。Lambda は読めなければ止まる。書き出し後に半径 300 m の検査をして、引っかかれば上げない。
- 同時処理：Lambda の同時実行の上限が 10 で予約できないため、`rides.json` は S3 の条件付き書き込み（ETag）で更新し、競合したら読み直す。
- 確認：`upload --ride ride_004 --parts raw` → S3 イベントで Lambda が起動し 19 秒で完了（初期化 10 秒、メモリ 502 MB）。retrain は 9 走行で完了し、新しい版 `20261107-143620` のベースラインの値は旧版と同じ、公開データ 37 ファイルは refactor 前のローカル出力とバイト単位で一致（rides.json は時刻だけ違う）。
- そのほか：S3 の `raw/` に memo.txt・readme.txt を上げた（以前の upload は .txt を上げていなかった）。`models/current.json` を作成。
- 気づき：コンテナは 1.6 GB で初期化が約 10 秒かかる（Lambda の初期化の上限付近）。気になるなら folium・plotly を外す（viz.py への依存を切る）と軽くなる。
- 次：C（ESP32 から Wi-Fi で直接 S3 に送る）。D（SageMaker）は後回し。

## C：ESP32 から S3 へ直接送る ― サーバー側（2026-11-08 実施）

- 設計：`docs/device_upload_design.md`。送るきっかけは「止まって静か 2 分で自動＋BOOT ボタン 2 秒」（本人決定）。記録と送信は同時にしない（core 0 の取り合いとメモリ）。送り方は署名付き URL（機器は AWS の鍵を持たず、取り消せる機器トークンだけ）。
- できたこと：デバイス API（`D:/ct125-app/api` の `device_main.py`、Lambda `ct125-device-api`。画面用のデータ API とは別の関数・別の権限）。`POST /api/device/uploads`（走行名 `ride_<日時>` と 15 分の PUT 用 URL）、`POST /api/device/uploads/{ride_id}/complete`（大きさを確かめて `upload_complete.json` → B の自動処理）。機器登録 `register-device` / `revoke-device`（トークンのハッシュだけを SSM `/ct125/devices/<ID>/token-sha256`）、お手本 `tools/device_upload_simulator.py`。API のテスト 51 件、ct125-logger のテスト 50 件。
- 確認：公開ドメイン経由で、トークンなし・違うトークン・登録の無い機器はすべて 401（後の 2 つは同じ文言）。機器のふりで ride_001 を送り、受け付け → PUT → 完了 → 自動処理 → 公開一覧（10 走行）まで通った。完了をもう一度呼んでも already_complete。確認後、テストの走行（raw・processed・公開データ・rides.json の 1 件）と機器 sim01 の登録は消した。
- 途中で直したこと：boto3 の既定のクライアントだと署名付き URL が古い SigV2・グローバルのエンドポイントになる（ESP32 はリダイレクトに対応できない）。SigV4・リージョンのエンドポイントに固定した（テストで確認）。
- 次：ファームウェア。その前に本人に確認：家の Wi-Fi（2.4GHz）とテザリングの有無、ブレッドボードで BOOT ボタンを押せるか。Wi-Fi のパスワードとトークンの書き込みは本人が行う。

## C：ファームウェア V3（2026-11-08 実施）

- できたこと：`CT125_LOGGER_V3.0`。記録中 →（一度動いた後、静か 2 分／BOOT ボタン 2 秒／シリアルの `UPLOAD`）→ 記録を閉じる（タスクを止め、リングバッファを書き切って解放）→ Wi-Fi・NTP・HTTPS で送信 → 待機（3 秒続けて動いたら再起動して次の記録）。送信の手順は `uploader.cpp`（シミュレーターと同じ）、URL の期限切れは 1 回だけ出し直し、途中で切れたら `upload_state.json` から続き、送り終えたら `uploaded.json`。V2 までの走行と 30 秒未満の走行は送らない。ルート証明書は Amazon Root CA 1 と Starfield G2（API と S3 の両方がこれにつながることを openssl で確認）。Wi-Fi とトークンは NVS（`config_store.cpp`、シリアルの `CFG SET`。値は出さない）。設定は `scripts/provision-device.ps1`（パスワードは本人が入力、トークンのファイルは書き込み後に消す）。
- 確認：コンパイル 1.13MB（既定のパーティションの 86%）。COM5 の ESP32（D0WD-V3 rev3.1）に書き込み、記録 399.2Hz・取りこぼし 0・GPS 有効（衛星 20）、`CFG STATUS` に応答（未設定）。機器 d01 を登録（トークンは config/d01.token、.gitignore 済み）。
- 未確認：Wi-Fi の設定（本人）→ BOOT ボタンで送信 → AWS の自動処理 → 公開。バッテリーでの「静か 2 分」の自動送信。実走。
- 注意：机上で送った走行は公開一覧に載る（止まったままの試験データ）。確認が済んだら消す。

## C：ESP32 から S3 へ送れた（2026-11-08 実施、V3.1）

- 本人が `provision-device.ps1` で Wi-Fi（家のルーターの 2.4GHz）と機器トークン d01 を書き込み、机上で送信を確認：SD の ride_013（約 5 分、accel 4.3MB）→ デバイス API → S3 `raw/ride_20261108_011304/`（4.3MB を約 33 秒、約 130KB/s）→ 完了 → B の Lambda（窓 291）→ 公開一覧に 10 件目として載った。**C → B → 公開の全体が初めて機器から通った。**
- 1 回目の失敗：BOOT ボタンで始めた送信が、最初のファイルの前に止まった（LED 3 回点滅）。SD のログに ticket だけが残り put の記録が無いことから、ボタンを押す手の揺れを「動き出した」と判定して送信をやめたと判断。V3.1 で、手で始めた送信（BOOT・シリアル）はやめないように、自動の送信は動きが約 1 秒続いたときだけやめるように直した。やめたときは `/upload_log.csv` に aborted を残す。シリアルの `LOG` で SD を抜かずにログが読める。
- 机上の試験の走行 ride_20261108_011304 は、本人が画面で見た後に消した（raw・processed・公開データ・rides.json の 1 件。公開一覧は 9 走行に戻した）。ESP32 の SD の ride_013 には uploaded.json があるので、もう一度送られることはない。
- 未確認：バッテリーでの「静か 2 分」からの自動送信、実走。
