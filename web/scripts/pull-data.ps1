# S3 の app/v1/ を cache/ に写す（回線なしで触るとき・1 ファイルビルドの前）。
# 設定は .env.local（AWS_PROFILE・AWS_REGION・S3_BUCKET・S3_PREFIX）。
# S3 に rides.json が無いときは何もしない（空の S3 と同期して cache/ を消してしまわないように）。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env.local"
if (-not (Test-Path $envFile)) { throw ".env.local がありません。.env.example をコピーして値を入れてください" }

$cfg = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { $cfg[$matches[1]] = $matches[2] }
}
$profileName = if ($cfg["AWS_PROFILE"]) { $cfg["AWS_PROFILE"] } else { "ct125-logger" }
$region = if ($cfg["AWS_REGION"]) { $cfg["AWS_REGION"] } else { "ap-northeast-1" }
$bucket = $cfg["S3_BUCKET"]
$prefix = if ($cfg["S3_PREFIX"]) { $cfg["S3_PREFIX"] } else { "app/v1/" }
if (-not $bucket -or $bucket.Contains("<")) { throw ".env.local の S3_BUCKET が未設定です" }

$cache = Join-Path $root "cache"
$src = "s3://$bucket/$prefix"
Write-Host "S3 の $src を確認しています（プロファイル $profileName）"
# PowerShell 5.1 では Stop のままだと aws のエラー出力が止まるエラーになるので、この確認の間だけ Continue にする
$ErrorActionPreference = "Continue"
aws s3api head-object --bucket $bucket --key "${prefix}rides.json" --profile $profileName --region $region 2>$null | Out-Null
$found = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $found) {
    Write-Host "$src に rides.json がありません（または認証が切れています）。cache/ は変更しません。" -ForegroundColor Yellow
    Write-Host "データを上げるには ct125-logger で: python -m ct125 export --upload"
    exit 1
}

# --delete：S3 に無くなったファイルは cache/ からも消す（.gitkeep は残す）
aws s3 sync $src $cache --delete --exclude ".gitkeep" --profile $profileName --region $region
if ($LASTEXITCODE -ne 0) { throw "aws s3 sync に失敗しました" }
$n = (Get-ChildItem $cache -File | Where-Object { $_.Name -ne ".gitkeep" }).Count
Write-Host "cache/ に $n ファイル（$src から）"
