# Web アプリを CloudFront に出す（-Env test なら test の環境。既定は本番）：
#   1. Terraform の出力からログインの設定（.env.production.local）を作る
#   2. npm run build（hosted 版。走行データは入らない。データはログイン後に /api/data/ から取る）
#   3. S3 の webapp/ に上げる（index.html はキャッシュさせない、assets/ は長くキャッシュ）
#   4. CloudFront のキャッシュを消す
# 前提：infra で terraform apply 済み、AWS プロファイル ct125-logger でログイン済み
#   -Env test : test の環境に出す（Terraform の workspace の test を読む。docs/test_environment.md）
param([Alias("Env")][ValidateSet("prod", "test")][string]$Environment = "prod")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$terraformDir = if ($env:CT125_TERRAFORM_DIR) { $env:CT125_TERRAFORM_DIR } else { Join-Path (Split-Path -Parent $root) "infra" }
$awsProfile = "ct125-logger"
$isProd = $Environment -eq "prod"

function Get-TerraformOutputs {
    # 選んでいる workspace に関わらず、-Env の環境の出力を読む（本番は default）
    $previousWorkspace = $env:TF_WORKSPACE
    $env:TF_WORKSPACE = if ($isProd) { "default" } else { $Environment }
    try { $json = terraform "-chdir=$terraformDir" output -json }
    finally { $env:TF_WORKSPACE = $previousWorkspace }
    if ($LASTEXITCODE -ne 0) { throw "terraform output に失敗しました（$terraformDir、$Environment）" }
    $outputs = $json | ConvertFrom-Json
    # まだ apply していない workspace は、出力が空になる
    if (-not $outputs.work_bucket_name) { throw "Terraform の $Environment の環境に出力がありません（まだ作っていないか、terraform init がまだ）" }
    # env の出力が無い（古い state）のは本番だけ
    $actual = if ($outputs.env) { $outputs.env.value } else { "prod" }
    if ($actual -ne $Environment) { throw "Terraform の出力の環境（$actual）が -Env（$Environment）と違います" }
    return $outputs
}

. (Join-Path $PSScriptRoot "auth-env.ps1")

function Write-AuthEnv($outputs) {
    $path = Join-Path $root ".env.production.local"
    Write-AuthEnvFile $path "# scripts/deploy.ps1 が Terraform の出力から作る。手で直さない（秘密の値はない）" $outputs
    # dev 用にコミットしてある .env.development（本番の値）も、Terraform の出力とずれていれば直す
    if ($isProd) { Sync-CommittedAuthEnv $root $outputs }
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
    Write-Host "公開しました（$Environment）：$($outputs.app_url.value)"
}
finally {
    Pop-Location
}
