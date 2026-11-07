# 走行データ処理の Lambda 用コンテナを作り、ECR に上げる。
#   1. docker build（deploy/lambda/Dockerfile、linux/amd64）
#   2. ECR にログインして push
#   3. 上げたイメージの digest を Terraform の変数ファイル（pipeline_image.auto.tfvars）に書く
# その後 `terraform -chdir=D:/ct125-logger-terraform apply` で Lambda が新しいイメージに切り替わる。
# 前提：Docker Desktop が起動していること、Terraform で ECR リポジトリを作ってあること（terraform output pipeline_repository_url）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$terraformDir = if ($env:CT125_TERRAFORM_DIR) { $env:CT125_TERRAFORM_DIR } else { "D:\ct125-logger-terraform" }
$awsProfile = "ct125-logger"
$tag = Get-Date -Format "yyyyMMdd-HHmmss"

function Get-RepositoryUrl {
    $url = terraform "-chdir=$terraformDir" output -raw pipeline_repository_url
    if ($LASTEXITCODE -ne 0 -or -not $url) { throw "ECR リポジトリの URL を取れません（terraform apply 済みか確認）" }
    return $url
}

function Invoke-Checked([scriptblock]$command, [string]$message) {
    # docker は進み具合を stderr に出す。PowerShell 5.1 はそれをエラー扱いにするので、成否は終了コードだけで見る
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $command 2>&1 | ForEach-Object { "$_" } }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw $message }
}

$repositoryUrl = Get-RepositoryUrl
$registry = $repositoryUrl.Split("/")[0]
$image = "$($repositoryUrl):$tag"

Push-Location $root
try {
    Invoke-Checked { docker build --platform linux/amd64 --provenance=false -f deploy/lambda/Dockerfile -t $image . } "docker build に失敗しました（Docker Desktop が起動しているか確認）"
    # PowerShell 5.1 のパイプは文字コードを変えてしまい ECR が 400 を返すので、cmd のパイプで渡す（トークンは画面に出さない）
    Invoke-Checked { cmd /c "aws ecr get-login-password --profile $awsProfile | docker login --username AWS --password-stdin $registry" } "ECR にログインできません"
    Invoke-Checked { docker push $image } "docker push に失敗しました"
    $digest = docker inspect --format "{{index .RepoDigests 0}}" $image
    if ($LASTEXITCODE -ne 0 -or -not $digest) { throw "イメージの digest を取れません" }

    $tfvars = Join-Path $terraformDir "pipeline_image.auto.tfvars"
    $lines = @("# scripts/build-pipeline-image.ps1 が書く。手で直さない", "pipeline_image_uri = `"$digest`"")
    [IO.File]::WriteAllLines($tfvars, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "上げました：$digest"
    Write-Host "次に：terraform -chdir=$terraformDir apply"
}
finally {
    Pop-Location
}
