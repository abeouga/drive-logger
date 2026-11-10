# Vite の dev サーバーを起動して、ブラウザで http://localhost:5173 を開く。
#   すでに起動していれば、ブラウザを開くだけ。止めるときはこの画面で Ctrl+C。
#   -NoBrowser : ブラウザを開かない
param([switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$port = 5173
$url = "http://localhost:$port/"
Set-Location $root
$Host.UI.RawUI.WindowTitle = "ct125-app dev server ($url)"

# Vite は localhost で待ち受ける。Node では IPv6（::1）だけのことがあるので、IPv4 と IPv6 の両方を見る
$portCheck = {
    param([int]$p)
    foreach ($pair in @(@("127.0.0.1", "InterNetwork"), @("::1", "InterNetworkV6"))) {
        $client = New-Object System.Net.Sockets.TcpClient([System.Net.Sockets.AddressFamily]$pair[1])
        try {
            $ar = $client.BeginConnect($pair[0], $p, $null, $null)
            if ($ar.AsyncWaitHandle.WaitOne(300) -and $client.Connected) { return $true }
        } catch { } finally { $client.Close() }
    }
    return $false
}
function Test-Port([int]$p) { return (& $portCheck $p) }

# すでに動いていれば開くだけ
if (Test-Port $port) {
    Write-Host "dev サーバーはもう起動しています：$url"
    if (-not $NoBrowser) { Start-Process $url }
    exit 0
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm が見つかりません。Node.js を入れてください" }

if (-not (Test-Path (Join-Path $root "node_modules"))) {
    Write-Host "初回なので依存パッケージを入れます（npm install）..."
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw "npm install に失敗しました" }
}

# ログインの設定を Terraform の出力から .env.development.local に作る（公開版の deploy.ps1 と同じ値。秘密ではない）。
# Terraform が読めない PC（AWS のログインや terraform init がまだ）でも、コミットしてある .env.development の値で起動を続ける
. (Join-Path $PSScriptRoot "auth-env.ps1")
$envFile = Join-Path $root ".env.development.local"
$terraformDir = Join-Path (Split-Path -Parent $root) "infra"
$ok = $false
$terraformError = ""
if (Get-Command terraform -ErrorAction SilentlyContinue) {
    $errFile = [IO.Path]::GetTempFileName()
    try {
        $ErrorActionPreference = "Continue"
        $json = terraform "-chdir=$terraformDir" output -no-color -json 2>$errFile
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        $terraformError = [IO.File]::ReadAllText($errFile)
    } finally {
        Remove-Item $errFile -ErrorAction SilentlyContinue
    }
}
if ($ok) {
    $outputs = $json | ConvertFrom-Json
    Write-AuthEnvFile $envFile "# scripts/start-dev.ps1 が Terraform の出力から作る。手で直さない（秘密の値はない）" $outputs
    Sync-CommittedAuthEnv $root $outputs
    Write-Host "ログインの設定を作りました（$envFile）。データは公開ドメインのデータ API から読みます（ログインが要ります）"
} else {
    $hint = Get-TerraformFailureHint $terraformDir "ct125-logger" $terraformError
    Write-Host "Terraform の出力を読めませんでした：$hint" -ForegroundColor Yellow
    if (Test-Path $envFile) {
        Write-Host "前に作った $envFile のログインの設定で起動します" -ForegroundColor Yellow
    } else {
        Write-Host "コミットしてある .env.development のログインの設定で起動します（画面を見るだけならこのままでよい）" -ForegroundColor Yellow
    }
}

# 起動を待ってブラウザを開く（裏で待つ）
if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($p, $u, $checkText)
        $check = [scriptblock]::Create($checkText)
        for ($i = 0; $i -lt 60; $i++) {
            if (& $check $p) { Start-Process $u; return }
            Start-Sleep -Milliseconds 500
        }
    } -ArgumentList $port, $url, $portCheck.ToString() | Out-Null
}

Write-Host "dev サーバーを起動します：$url （止めるときは Ctrl+C）"
npm run dev
$code = $LASTEXITCODE
Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
exit $code
