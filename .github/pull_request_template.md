# Pull Request

## 変更内容

このPRで変更した内容を簡潔に記載してください。

- 
- 

## 対応Issue

例：Closes #12

## 変更したフォルダー

- [ ] firmware
- [ ] pipeline
- [ ] api
- [ ] web
- [ ] infra
- [ ] docs

## 動作確認

変更したフォルダーの分だけ実施してください。

- [ ] firmware：コンパイルが通る。実機に書き込み、SD・ADXL・GPS が OK、取りこぼし 0
- [ ] pipeline：`cd pipeline; .venv/Scripts/python -m pytest` が通る
- [ ] api：`cd api; .venv/Scripts/python -m pytest` が通る
- [ ] web：`npm run typecheck` と `npm run build` が通る
- [ ] infra：`terraform -chdir=infra plan` の差分が意図どおり（差分を下に貼る）
- [ ] 公開版（https://drive.herdio-system.com/）で確かめた

必要に応じて、具体的な確認手順を記載してください。

1. 
2. 

## フォルダーをまたぐ約束

CSV の形・送信の手順・画面用 JSON の形を変えた場合は、作る側と使う側を同じ PR で直してください。

- [ ] 約束は変えていない
- [ ] 変えた（作る側と使う側の両方を直した。内容：　　）

## 影響範囲

例：

- `datasets/shared/rides.json`（公開用のバケット）
- Lambda `ct125-ride-pipeline`
- `POST /api/device/uploads`

## AWS への影響

- [ ] AWS のリソース・費用に影響しない
- [ ] 影響する（作る・変える・消すもの、費用の目安：　　）

## レビューしてほしい点

- 

## 未対応事項

- なし

## チェックリスト

- [ ] 対応するIssueが存在し、完了条件を満たしている
- [ ] 秘密（AWS の鍵・トークン・Wi-Fi の SSID とパスワード・tfvars・tfstate・.env）をコミットしていない
- [ ] 文章で「故障を予測できる」「精度 XX%」などと書いていない（docs/analysis_policy.md 1.2）
- [ ] K-Line の配線・回路には触れていない。ECU にはアダプター越しの読み出しの要求だけを送る（docs/analysis_policy.md 1.3）
- [ ] 不要なデバッグコード・ログ・コメントアウトを残していない
- [ ] 動きや決まりが変わる docs/ の文書・README を直した（必要な場合）
- [ ] 変更内容を自分で確認した
