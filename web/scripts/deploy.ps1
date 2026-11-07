# Web アプリを本番（CloudFront）に出す：
#   1. Terraform の出力からログインの設定（.env.production.local）を作る
#   2. npm run build（hosted 版。走行データは入らない。データはログイン後に /api/data/ から取る）
#   3. S3 の webapp/ に上げる（index.html はキャッシュさせない、assets/ は長くキャッシュ）
#   4. CloudFront のキャッシュを消す
# 前提：infra で terraform apply 済み、AWS プロファイル ct125-logger でログイン済み
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$terraformDir = if ($env:CT125_TERRAFORM_DIR) { $env:CT125_TERRAFORM_DIR } else { Join-Path (Split-Path -Parent $root) "infra" }
$awsProfile = "ct125-logger"

function Get-TerraformOutputs {
    $json = terraform "-chdir=$terraformDir" output -json
    if ($LASTEXITCODE -ne 0) { throw "terraform output に失敗しました（$terraformDir）" }
    return $json | ConvertFrom-Json
}

function Write-AuthEnv($outputs) {
    $lines = @(
        "# scripts/deploy.ps1 が Terraform の出力から作る。手で直さない（秘密の値はない）",
        "VITE_AUTH_AUTHORITY=$($outputs.auth_authority.value)",
        "VITE_AUTH_CLIENT_ID=$($outputs.auth_client_id.value)",
        "VITE_AUTH_DOMAIN=$($outputs.auth_domain.value)"
    )
    $path = Join-Path $root ".env.production.local"
    [IO.File]::WriteAllLines($path, $lines, [Text.UTF8Encoding]::new($false))
}

function Invoke-Build {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build に失敗しました" }
}

function Publish-Files($target) {
    $dist = Join-Path $root "dist"
    # 名前にハッシュが付いたファイルは中身が変わらないので、長くキャッシュしてよい
    aws s3 sync (Join-Path $dist "assets") "$($target)assets/" --delete --cache-control "public, max-age=31536000, immutable" --profile $awsProfile
    if ($LASTEXITCODE -ne 0) { throw "assets のアップロードに失敗しました" }
    # index.html は毎回最新を取らせる（新しい assets を指すため）
    aws s3 cp (Join-Path $dist "index.html") "$($target)index.html" --cache-control "no-cache" --profile $awsProfile
    if ($LASTEXITCODE -ne 0) { throw "index.html のアップロードに失敗しました" }
}

function Clear-CdnCache($distributionId) {
    aws cloudfront create-invalidation --distribution-id $distributionId --paths "/" "/index.html" --profile $awsProfile --query "Invalidation.Id" --output text
    if ($LASTEXITCODE -ne 0) { throw "CloudFront のキャッシュ削除に失敗しました" }
}

Push-Location $root
try {
    $outputs = Get-TerraformOutputs
    Write-AuthEnv $outputs
    Invoke-Build
    Publish-Files $outputs.webapp_s3_uri.value
    Clear-CdnCache $outputs.cloudfront_distribution_id.value
    Write-Host "公開しました：$($outputs.app_url.value)"
}
finally {
    Pop-Location
}
