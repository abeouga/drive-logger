# Lambda（Python 3.13・arm64）用の zip を dist/lambda.zip に作る。
# Windows でも Linux 用のパッケージ（manylinux・aarch64）を取ってくるので、Docker は要らない。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$build = Join-Path $root "build"
$package = Join-Path $build "package"
$dist = Join-Path $root "dist"
$zip = Join-Path $dist "lambda.zip"

Push-Location $root
try {
    if (Test-Path $build) { Remove-Item -Recurse -Force $build }
    New-Item -ItemType Directory -Force $package, $dist | Out-Null

    # 1. 本番の依存だけを、ロックファイルの版で書き出す（テスト用の依存は入れない）
    $requirements = Join-Path $build "requirements.txt"
    uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt -o $requirements -q
    if ($LASTEXITCODE -ne 0) { throw "uv export に失敗しました" }

    # 2. Lambda と同じ環境（Linux arm64・Python 3.13）用のパッケージを入れる
    uv pip install -r $requirements --target $package --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary :all: -q
    if ($LASTEXITCODE -ne 0) { throw "依存パッケージの取得に失敗しました" }

    # 3. このアプリのコードを足す
    Copy-Item -Recurse (Join-Path $root "src\ct125_api") (Join-Path $package "ct125_api")
    Get-ChildItem $package -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

    # 4. zip にまとめる
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Compress-Archive -Path (Join-Path $package "*") -DestinationPath $zip
    $sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
    Write-Host "できました：$zip（$sizeMb MB）"
}
finally {
    Pop-Location
}
