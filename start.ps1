# 画面（web/）の dev サーバーを起動して、ブラウザで http://localhost:5173 を開く。リポジトリの直下からの入口。
#   起動の手順は web/scripts/start-dev.ps1 にだけ書く（ここは呼ぶだけ）。
#   /api/* は公開ドメインのデータ API へ中継するので、公開版と同じログインが要る（web/docs/local_dev.md）。
#   すでに起動していれば、ブラウザを開くだけ。止めるときはこの画面で Ctrl+C。
#   -NoBrowser : ブラウザを開かない
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"

$startDev = Join-Path $PSScriptRoot "web\scripts\start-dev.ps1"
if (-not (Test-Path $startDev)) { throw "$startDev が見つかりません" }

# start-dev.ps1 は web/ に移って動く。PowerShell から .\start.ps1 で呼んだときに、元の場所へ戻す
$code = 1
Push-Location
try {
    & $startDev -NoBrowser:$NoBrowser
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
