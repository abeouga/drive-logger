# ログインの設定（VITE_AUTH_*）を扱う関数。scripts/start-dev.ps1 と scripts/deploy.ps1 が . で読み込む。
#   どの値も秘密ではない（ブラウザに配られる値）。

# Terraform の出力から、ログインの設定のファイル（.env.development.local / .env.production.local）を作る
function Write-AuthEnvFile([string]$path, [string]$header, $outputs) {
    $lines = @(
        $header,
        "VITE_AUTH_AUTHORITY=$($outputs.auth_authority.value)",
        "VITE_AUTH_CLIENT_ID=$($outputs.auth_client_id.value)",
        "VITE_AUTH_DOMAIN=$($outputs.auth_domain.value)"
    )
    [IO.File]::WriteAllLines($path, $lines, [Text.UTF8Encoding]::new($false))
}

# コミットしてある web/.env.development（Terraform が無い PC の dev 用）が Terraform の出力と違っていたら、
# 値の行だけを書き直して知らせる（コメントの行はそのまま残す）
function Sync-CommittedAuthEnv([string]$webRoot, $outputs) {
    $path = Join-Path $webRoot ".env.development"
    $want = [ordered]@{
        VITE_AUTH_AUTHORITY = "$($outputs.auth_authority.value)"
        VITE_AUTH_CLIENT_ID = "$($outputs.auth_client_id.value)"
    }
    $lines = if (Test-Path $path) { @([IO.File]::ReadAllLines($path)) } else { @() }
    $seen = @{}
    $changed = $false
    $out = foreach ($line in $lines) {
        if ($line -match '^([A-Z_]+)=(.*)$' -and $want.Contains($Matches[1])) {
            $key = $Matches[1]
            $seen[$key] = $true
            if ($Matches[2] -ne $want[$key]) { $changed = $true }
            "$key=$($want[$key])"
        } else {
            $line
        }
    }
    foreach ($key in $want.Keys) {
        if (-not $seen[$key]) { $changed = $true; $out = @($out) + "$key=$($want[$key])" }
    }
    if (-not $changed) { return }
    [IO.File]::WriteAllLines($path, [string[]]$out, [Text.UTF8Encoding]::new($false))
    Write-Host "ログインの設定が Terraform の出力と違っていたので $path を書き直しました。コミットしてください" -ForegroundColor Yellow
}

# Terraform の出力が読めなかった理由を、次にやることと一緒に返す（docs/setup_another_pc.md の手順に合わせる）
function Get-TerraformFailureHint([string]$terraformDir, [string]$awsProfile, [string]$terraformError) {
    # 調べるだけなので、aws の stderr で止めない（この関数の中だけ）
    $ErrorActionPreference = "Continue"
    $setupDoc = "docs/setup_another_pc.md"
    if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
        return "Terraform が入っていません（$setupDoc の 1.）"
    }
    if (Get-Command aws -ErrorAction SilentlyContinue) {
        $profiles = @(aws configure list-profiles 2>$null)
        if ($profiles -notcontains $awsProfile) {
            return "AWS のプロファイル $awsProfile がありません。aws configure set region ap-northeast-1 --profile $awsProfile と aws login --profile $awsProfile をしてください（$setupDoc の 3.）"
        }
    } else {
        return "AWS CLI が入っていません（$setupDoc の 1.）"
    }
    if (-not (Test-Path (Join-Path $terraformDir ".terraform"))) {
        return "infra/ で terraform init をしていません。terraform -chdir=infra init をしてください（$setupDoc の 5.）"
    }
    # terraform の枠線（│ ╷ ╵）を外して、最初の 1 行だけを見せる
    $first = $terraformError -split "`r?`n" | ForEach-Object { ($_ -replace '^[\s│╷╵]+', '').Trim() } | Where-Object { $_ } | Select-Object -First 1
    return "AWS のログインが切れているかもしれません。aws login --profile $awsProfile をしてください（Terraform のエラー：$first）"
}
