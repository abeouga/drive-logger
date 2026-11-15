# ログインの設定（VITE_AUTH_*）と dev の中継先（API_ORIGIN）を扱う関数。scripts/start-dev.ps1 と scripts/deploy.ps1 が . で読み込む。
#   どの値も秘密ではない（ブラウザに配られる値）。

# Terraform の出力から、その環境の設定のファイル（.env.development.local / .env.testenv.local / .env.production.local）を作る。
#   -WithApiOrigin：dev サーバーが /api/* を中継する先（API_ORIGIN＝その環境の画面の URL）も書く。ビルド（.env.production.local）では使わない
function Write-AuthEnvFile([string]$path, [string]$header, $outputs, [switch]$WithApiOrigin) {
    $lines = @(
        $header,
        "VITE_AUTH_AUTHORITY=$($outputs.auth_authority.value)",
        "VITE_AUTH_CLIENT_ID=$($outputs.auth_client_id.value)",
        "VITE_AUTH_DOMAIN=$($outputs.auth_domain.value)"
    )
    if ($WithApiOrigin) { $lines += "API_ORIGIN=$("$($outputs.app_url.value)".TrimEnd('/'))" }
    [IO.File]::WriteAllLines($path, $lines, [Text.UTF8Encoding]::new($false))
}

# 管理者の AWS のプロファイルの名前。Terraform の出力を読めないときの案内に使う。
#   環境変数 AWS_PROFILE、無ければ infra/terraform.tfvars（コミットしない）の aws_profile。どちらも無ければ空
function Get-AdminProfileName([string]$terraformDir) {
    if ($env:AWS_PROFILE) { return $env:AWS_PROFILE }
    $tfvars = Join-Path $terraformDir "terraform.tfvars"
    if (Test-Path $tfvars) {
        foreach ($line in [IO.File]::ReadAllLines($tfvars)) {
            if ($line -match '^\s*aws_profile\s*=\s*"([^"]+)"') { return $Matches[1] }
        }
    }
    return ""
}

# Terraform の出力が読めなかった理由を、次にやることと一緒に返す（docs/setup_another_pc.md の手順に合わせる）
function Get-TerraformFailureHint([string]$terraformDir, [string]$awsProfile, [string]$terraformError) {
    # 調べるだけなので、aws の stderr で止めない（この関数の中だけ）
    $ErrorActionPreference = "Continue"
    $setupDoc = "docs/setup_another_pc.md"
    if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
        return "Terraform が入っていません（$setupDoc の 1.）"
    }
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        return "AWS CLI が入っていません（$setupDoc の 1.）"
    }
    if (-not $awsProfile) {
        return "管理者の AWS のプロファイルが分かりません。infra/terraform.tfvars に aws_profile を書いてください（$setupDoc の 3.・5.）"
    }
    $profiles = @(aws configure list-profiles 2>$null)
    if ($profiles -notcontains $awsProfile) {
        return "AWS のプロファイル $awsProfile がありません。aws configure set region <AWS の project の Region> --profile $awsProfile と aws login --profile $awsProfile をしてください（$setupDoc の 3.）"
    }
    if (-not (Test-Path (Join-Path $terraformDir ".terraform"))) {
        return "infra/ で terraform init をしていません。infra/README.md の手順で terraform init をしてください（$setupDoc の 5.）"
    }
    # terraform の枠線（│ ╷ ╵）を外して、最初の 1 行だけを見せる
    $first = $terraformError -split "`r?`n" | ForEach-Object { ($_ -replace '^[\s│╷╵]+', '').Trim() } | Where-Object { $_ } | Select-Object -First 1
    return "AWS のログインが切れているかもしれません。aws login --profile $awsProfile をしてください（Terraform のエラー：$first）"
}
