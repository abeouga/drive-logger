# データ API を手元で動かす（画面の npm run dev:local の相手。ログインなしの「手元の開発者」＝ admin として扱う）。
#   バケットと処理の Lambda の名前は、Terraform の出力から読む（手で書き写さない）。
#   -Env test : test の環境のバケットと Lambda を使う（既定は本番。本番では admin の操作が本番のデータに効く）
#   -Port     : 待ち受けるポート（既定 8000。画面の LOCAL_API_ORIGIN と同じにする）
# 止めるときは Ctrl+C。手順は web/docs/local_dev.md と docs/test_environment.md
param(
    [Alias("Env")][ValidateSet("prod", "test")][string]$Environment = "prod",
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$terraformDir = if ($env:CT125_TERRAFORM_DIR) { $env:CT125_TERRAFORM_DIR } else { Join-Path (Split-Path -Parent $root) "infra" }

function Get-TerraformOutputs {
    # 選んでいる workspace に関わらず、-Env の環境の出力を読む（本番は default）
    $previousWorkspace = $env:TF_WORKSPACE
    $env:TF_WORKSPACE = if ($Environment -eq "prod") { "default" } else { $Environment }
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

$outputs = Get-TerraformOutputs
# Lambda と同じ環境変数（infra/data_api.tf）。ALLOW_LOCAL_USER は手元だけ
$settings = [ordered]@{
    AWS_PROFILE       = $outputs.aws_profile.value
    DATA_BUCKET       = $outputs.public_bucket_name.value
    WORK_BUCKET       = $outputs.work_bucket_name.value
    RAW_BUCKET        = $outputs.raw_bucket_name.value
    PIPELINE_FUNCTION = $outputs.pipeline_function_name.value
    ALLOW_LOCAL_USER  = "true"
}
# 終わったら、呼んだ画面の環境変数を元に戻す
$previous = @{}
foreach ($name in $settings.Keys) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    [Environment]::SetEnvironmentVariable($name, $settings[$name], "Process")
}

Push-Location $root
try {
    Write-Host "データ API を手元で動かします（向き先 $Environment、http://localhost:$Port、バケット $($settings.WORK_BUCKET) ほか）。止めるときは Ctrl+C"
    uv run uvicorn ct125_api.main:app --port $Port --app-dir src
}
finally {
    Pop-Location
    foreach ($name in $settings.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process") }
}
