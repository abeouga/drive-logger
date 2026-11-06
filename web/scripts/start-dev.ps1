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

if (-not (Test-Path (Join-Path $root ".env.local"))) {
    Write-Host ".env.local がありません。.env.example をコピーして値を入れてください（docs/local_dev.md）。" -ForegroundColor Yellow
    exit 1
}

# 設定を読む（表示と認証の確認だけに使う）
$cfg = @{}
Get-Content (Join-Path $root ".env.local") -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { $cfg[$matches[1]] = $matches[2] }
}
$source = if ($cfg["DATA_SOURCE"]) { $cfg["DATA_SOURCE"] } else { "s3" }
$profileName = if ($cfg["AWS_PROFILE"]) { $cfg["AWS_PROFILE"] } else { "ct125-logger" }

if (-not (Test-Path (Join-Path $root "node_modules"))) {
    Write-Host "初回なので依存パッケージを入れます（npm install）..."
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw "npm install に失敗しました" }
}

if ($source -eq "s3") {
    # PowerShell 5.1 では Stop のままだと aws のエラー出力が止まるエラーになるので、確認の間だけ Continue にする
    $ErrorActionPreference = "Continue"
    aws sts get-caller-identity --profile $profileName 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = "Stop"
    if ($ok) {
        Write-Host "データ：S3（プロファイル $profileName）"
    } else {
        Write-Host "AWS の認証を確認できませんでした（プロファイル $profileName）。S3 から取れないファイルは cache/ の写しを使います。" -ForegroundColor Yellow
    }
} else {
    Write-Host "データ：cache/（DATA_SOURCE=$source）"
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
