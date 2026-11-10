# contracts：フォルダーをまたぐ約束（機械が読める定義）

firmware・pipeline・api・web の間でやりとりするファイルと JSON の形を、ここに 1 か所だけ書く。
各フォルダーのコードは定数や型を持つが、**それがここの定義と合っているかをテストで突き合わせる**（下の表）。
約束を変えるときは、ここを直し、作る側と使う側を同じ PR で直す。

| 約束 | 定義 | 作る側 | 使う側 |
|---|---|---|---|
| 共通の決まり（走行 ID・機器 ID・止まっているとみなす速さ） | `common.json` | — | 全部 |
| SD の 1 回の記録（フォルダーのファイル） | `sd/session.json` | firmware | pipeline・api |
| SD の CSV（加速度・GPS・出来事・状態・送信の記録） | `sd/*.table.json`（[Table Schema](https://specs.frictionlessdata.io/table-schema/)） | firmware | pipeline |
| `meta.json`・`uploaded.json`・`upload_state.json` | `sd/*.schema.json`（JSON Schema） | firmware | pipeline・firmware |
| 機器からの送信の手順 | `upload/upload.json`・`upload/*.schema.json` | firmware・PC のツール | api（デバイス API）・pipeline |
| 画面用 JSON（`rides.json`・`ride_<id>.json`・`spec_<id>.json`・`wave_<id>_<chunk>.json`） | `app/*.schema.json` | pipeline（export） | api・web |
| 走行の台帳・処理の記録・モデルの記録 | `records/*.schema.json` | pipeline | api・web |
| データ API の要求と応答（走行の一覧・処理の記録・モデルの一覧・完全に削除） | `api/*.schema.json` | api | web |

- JSON Schema は Draft 2020-12。どの定義にも `version`（整数）を持たせ、形を変えたら上げる
- 画面用 JSON の見本は `examples/app/`。pipeline のテストが、本物の書き出しの関数から作り直して一致を確かめ、web の型チェック（`web/src/lib/contract.check.ts`）がこの見本を型に当てる
- 走行の台帳・処理の記録・モデルの記録は、設計（[docs/data_flow_design.md](../docs/data_flow_design.md)）の形を先に定義したもの。実装は #10・#11

## 突き合わせのテスト

| どこ | 何を確かめるか |
|---|---|
| `contracts/tests/` | 定義そのものが正しい JSON Schema か、見本が定義に合うか、firmware のソースの定数（送るファイル・止まる速さ・CSV の列・出来事の種類）が定義と同じか |
| `pipeline/tests/test_contracts.py` | 読み込み（io.py）の列と必須のファイル、送るファイル、走行 ID の決まり、書き出し（export.py）の JSON が定義に合うか、見本が書き出しの関数と一致するか |
| `api/tests/test_contracts.py` | デバイス API の受け付けるファイル・必須のファイル・走行 ID・SD のセッション名・機器 ID の決まり、要求と応答の JSON が定義に合うか |
| `web/src/lib/contract.check.ts` | 画面用 JSON の見本が `types.ts` の型に合うか（`npm run typecheck`） |

CI（`.github/workflows/ci.yml`）が PR ごとに全部を回す。

手元で回す：

```bash
uv run --no-project --with jsonschema==4.26.0 --with pytest==9.2.0 --with pyyaml==6.0.3 python -m pytest contracts/tests -q
```
