# 配布用の 1 ファイル（dist/index.html）を作る：S3 から cache/ を更新 → npm run build → 自宅周辺の座標がないか検査。
#   -NoPull  : S3 から取り直さず、今の cache/ でビルドする
# 検査には ct125-logger の check-privacy を使う（自宅座標は ct125-logger の config/local.yaml にあり、このフォルダーには置かない）。
param([switch]$NoPull)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logger = if ($env:CT125_LOGGER_DIR) { $env:CT125_LOGGER_DIR } else { Join-Path (Split-Path -Parent $root) "pipeline" }
$python = Join-Path $logger ".venv\Scripts\python.exe"

if (-not $NoPull) {
    & (Join-Path $PSScriptRoot "pull-data.ps1")
    if ($LASTEXITCODE -ne 0) { throw "pull-data に失敗しました（-NoPull で今の cache/ のままビルドできます）" }
}

Push-Location $root
try {
    npm run build:single
    if ($LASTEXITCODE -ne 0) { throw "npm run build:single に失敗しました" }
} finally {
    Pop-Location
}

$html = Join-Path $root "dist\index.html"
if (-not (Test-Path $python)) { throw "ct125-logger の Python が見つかりません：$python（環境変数 CT125_LOGGER_DIR で場所を指定）" }
Push-Location $logger
try {
    & $python -m ct125 check-privacy $html
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) {
    Write-Host "検査に通りませんでした。dist/index.html を配らないでください。" -ForegroundColor Red
    exit $code
}
$size = [math]::Round((Get-Item $html).Length / 1MB, 1)
Write-Host "できました：$html（$size MB）。S3 へは ct125-logger で: python -m ct125 upload --site-app $html"
