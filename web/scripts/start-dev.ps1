# Vite の dev サーバーを起動して、ブラウザで http://localhost:5173 を開く。
#   すでに起動していれば、ブラウザを開くだけ。止めるときはこの画面で Ctrl+C。
#   -NoBrowser : ブラウザを開かない
#   -Env test  : test の環境につなぐ（npm run dev:test。/api/* は test のドメイン、ログインは test の Cognito。docs/test_environment.md）
param([switch]$NoBrowser, [Alias("Env")][ValidateSet("prod", "test")][string]$Environment = "prod")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$port = 5173
$url = "http://localhost:$port/"
Set-Location $root
$Host.UI.RawUI.WindowTitle = "ct125-app dev server ($url, $Environment)"
$isProd = $Environment -eq "prod"
# Vite の mode：本番は development（.env.development*）、test は testenv（.env.testenv*）
$envFileName = if ($isProd) { ".env.development.local" } else { ".env.testenv.local" }
$npmScript = if ($isProd) { "dev" } else { "dev:test" }

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
$envFile = Join-Path $root $envFileName
$terraformDir = Join-Path (Split-Path -Parent $root) "infra"
$ok = $false
$terraformError = ""
if (Get-Command terraform -ErrorAction SilentlyContinue) {
    $errFile = [IO.Path]::GetTempFileName()
    # 選んでいる workspace に関わらず、-Env の環境の出力を読む（本番は default）。終わったら元に戻す
    $previousWorkspace = $env:TF_WORKSPACE
    $env:TF_WORKSPACE = if ($isProd) { "default" } else { $Environment }
    try {
        $ErrorActionPreference = "Continue"
        $json = terraform "-chdir=$terraformDir" output -no-color -json 2>$errFile
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        $terraformError = [IO.File]::ReadAllText($errFile)
    } finally {
        Remove-Item $errFile -ErrorAction SilentlyContinue
        $env:TF_WORKSPACE = $previousWorkspace
    }
}
if ($ok) {
    $outputs = $json | ConvertFrom-Json
    # まだ apply していない workspace は、出力が空になる
    if (-not $outputs.work_bucket_name) { throw "Terraform の $Environment の環境に出力がありません（まだ作っていないか、terraform init がまだ）" }
    # env の出力が無い（古い state）のは本番だけ
    $actual = if ($outputs.env) { $outputs.env.value } else { "prod" }
    if ($actual -ne $Environment) { throw "Terraform の出力の環境（$actual）が -Env（$Environment）と違います" }
    Write-AuthEnvFile $envFile "# scripts/start-dev.ps1 が Terraform の出力から作る。手で直さない（秘密の値はない）" $outputs
    if ($isProd) { Sync-CommittedAuthEnv $root $outputs }
    Write-Host "ログインの設定を作りました（$envFile）。データは $($outputs.app_url.value) のデータ API から読みます（ログインが要ります）"
} elseif (-not $isProd -and -not (Test-Path $envFile)) {
    # test にはコミットしたログインの設定が無い（本番の設定で test に入ることはできない）
    $hint = Get-TerraformFailureHint $terraformDir "ct125-logger" $terraformError
    throw "test のログインの設定を Terraform の出力から作れませんでした：$hint"
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

Write-Host "dev サーバーを起動します：$url （向き先 $Environment。止めるときは Ctrl+C）"
npm run $npmScript
$code = $LASTEXITCODE
Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
exit $code
