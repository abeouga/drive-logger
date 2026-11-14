# 走行データ処理の Lambda 用コンテナを作り、ECR に上げる。
#   1. docker build（deploy/lambda/Dockerfile、linux/amd64）
#   2. ECR にログインして push
#   3. 上げたイメージの digest（sha256:…。ECR の住所は書かない）を Terraform の変数ファイル（本番 pipeline_image.auto.tfvars、test pipeline_image.test.tfvars）に書く
# その後 infra で apply すると、Lambda が新しいイメージに切り替わる。
# 前提：Docker Desktop が起動していること、Terraform で ECR リポジトリを作ってあること（terraform output pipeline_repository_url）
#   -Env test : test の ECR に上げる（Terraform の workspace の test を読む。docs/test_environment.md）
param([Alias("Env")][ValidateSet("prod", "test")][string]$Environment = "prod")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$terraformDir = if ($env:CT125_TERRAFORM_DIR) { $env:CT125_TERRAFORM_DIR } else { Join-Path (Split-Path -Parent $root) "infra" }
# 選んでいる workspace に関わらず、-Env の環境の出力を読む（本番は default）。終わったら元に戻す
$previousWorkspace = $env:TF_WORKSPACE
$env:TF_WORKSPACE = if ($Environment -eq "prod") { "default" } else { $Environment }
$tag = Get-Date -Format "yyyyMMdd-HHmmss"

function Assert-Env {
    $actual = terraform "-chdir=$terraformDir" output -raw env 2>$null
    # env の出力が無い（古い state）のは本番だけ
    if ($LASTEXITCODE -ne 0 -or -not $actual) { $actual = "prod" }
    if ($actual -ne $Environment) { throw "Terraform の出力の環境（$actual）が -Env（$Environment）と違います" }
}

# ECR にログインするプロファイルは、Terraform と同じもの（出力の aws_profile。infra/terraform.tfvars に書く）
function Get-AwsProfile {
    $name = terraform "-chdir=$terraformDir" output -raw aws_profile
    if ($LASTEXITCODE -ne 0 -or -not $name) { throw "Terraform の出力に aws_profile がありません（terraform apply 済みか確認）" }
    return $name
}

function Get-RepositoryUrl {
    $url = terraform "-chdir=$terraformDir" output -raw pipeline_repository_url
    if ($LASTEXITCODE -ne 0 -or -not $url) { throw "ECR リポジトリの URL を取れません（terraform apply 済みか確認）" }
    return $url
}

# 新しい処理（S3 を中心にした 1 本の流れ）は、作業用・公開用のバケットが要る（infra の #6）。
# それより前の Terraform のまま新しいコンテナを入れると、Lambda が環境変数を読めずに止まるので、先に確かめる
function Assert-NewBuckets {
    $work = terraform "-chdir=$terraformDir" output -raw work_bucket_name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $work) {
        throw "Terraform に作業用のバケット（work_bucket_name）がありません。先に infra を作り直しに合わせてください（docs/data_flow_design.md 12.）"
    }
}

function Get-Commit {
    $commit = git -C $root rev-parse --short HEAD
    if ($LASTEXITCODE -ne 0 -or -not $commit) { return "unknown" }
    $dirty = git -C $root status --porcelain -- src config deploy
    if ($dirty) { return "$commit-dirty" }
    return $commit
}

function Invoke-Checked([scriptblock]$command, [string]$message) {
    # docker は進み具合を stderr に出す。PowerShell 5.1 はそれをエラー扱いにするので、成否は終了コードだけで見る
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $command 2>&1 | ForEach-Object { "$_" } }
    finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw $message }
}

Push-Location $root
try {
    Assert-Env
    Assert-NewBuckets
    $repositoryUrl = Get-RepositoryUrl
    $awsProfile = Get-AwsProfile
    $commit = Get-Commit
    $registry = $repositoryUrl.Split("/")[0]
    $image = "$($repositoryUrl):$tag"

    Invoke-Checked { docker build --platform linux/amd64 --provenance=false --build-arg "GIT_COMMIT=$commit" -f deploy/lambda/Dockerfile -t $image . } "docker build に失敗しました（Docker Desktop が起動しているか確認）"
    # PowerShell 5.1 のパイプは文字コードを変えてしまい ECR が 400 を返すので、cmd のパイプで渡す（トークンは画面に出さない）
    Invoke-Checked { cmd /c "aws ecr get-login-password --profile $awsProfile | docker login --username AWS --password-stdin $registry" } "ECR にログインできません"
    Invoke-Checked { docker push $image } "docker push に失敗しました"
    # RepoDigests は <ECR の住所>@sha256:…。住所（アカウント ID とリージョンが入る）は Terraform がこの環境の ECR から組み立てるので、digest だけを書く
    $repoDigest = docker inspect --format "{{index .RepoDigests 0}}" $image
    if ($LASTEXITCODE -ne 0 -or -not $repoDigest) { throw "イメージの digest を取れません" }
    $digest = ($repoDigest -split "@", 2)[1]
    if ($digest -notmatch '^sha256:[0-9a-f]{64}$') { throw "イメージの digest の形が違います：$repoDigest" }

    if ($Environment -eq "prod") {
        $tfvars = Join-Path $terraformDir "pipeline_image.auto.tfvars"
        $lines = @("# pipeline/scripts/build-pipeline-image.ps1 が書く。手で直さない（ECR の住所は書かない。この環境の ECR から組み立てる）", "pipeline_image_digest = `"$digest`"")
        $next = "terraform -chdir=$terraformDir apply"
    } else {
        $tfvars = Join-Path $terraformDir "pipeline_image.$Environment.tfvars"
        $lines = @("# pipeline/scripts/build-pipeline-image.ps1 -Env $Environment が書く。手で直さない（ECR の住所は書かない。この環境の ECR から組み立てる）", "pipeline_image_digest = `"$digest`"")
        $next = "terraform -chdir=$terraformDir workspace select $Environment; terraform -chdir=$terraformDir apply -var-file=$Environment.tfvars -var-file=pipeline_image.$Environment.tfvars"
    }
    [IO.File]::WriteAllLines($tfvars, $lines, [Text.UTF8Encoding]::new($false))
    Write-Host "上げました（$Environment）：$digest"
    Write-Host "次に：$next"
}
finally {
    Pop-Location
    $env:TF_WORKSPACE = $previousWorkspace
}
