# ESP32 に Wi-Fi と機器トークンを書き込む（ESP32 の内部フラッシュ NVS に入る。SD やソースには残らない）。
#   例：./scripts/provision-device.ps1 -Port <ポート> -Ssid <2.4GHz の SSID> -DeviceId d01 -TokenFile config/d01.token
# Wi-Fi のパスワードはこの画面で入力する（表示されない・どこにも保存しない）。
# トークンのファイルは、書き込みが確認できたら消す（必要になったら register-device --rotate で作り直す）。
# 前提：V3 のファームウェアを書き込み済み、ESP32 を USB でつないでいる、シリアルモニターなどほかでポートを開いていない。
param(
    [Parameter(Mandatory = $true)][string]$Port,
    [Parameter(Mandatory = $true)][string]$Ssid,
    [Parameter(Mandatory = $true)][string]$DeviceId,
    [Parameter(Mandatory = $true)][string]$TokenFile,
    [string]$ApiBase = ""
)
$ErrorActionPreference = "Stop"

function Read-Secret([string]$prompt) {
    $secure = Read-Host $prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

# 1 行送り、"CFG OK <キー>" が返るまで待つ。送った値は表示しない
function Send-Setting([IO.Ports.SerialPort]$serial, [string]$key, [string]$value) {
    if ($value -match "\s") { throw "$key に空白は使えません" }
    $serial.WriteLine("CFG SET $key $value")
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        try { $line = $serial.ReadLine().Trim() } catch [TimeoutException] { continue }
        if ($line -eq "CFG OK $key") { Write-Host "  書き込みました：$key"; return }
        if ($line.StartsWith("CFG ERR")) { throw "ESP32 が断りました：$line" }
    }
    throw "ESP32 から $key の返事がありません（ファームウェアが V3 か、ポートが合っているか確認）"
}

function Show-Status([IO.Ports.SerialPort]$serial) {
    $serial.WriteLine("CFG STATUS")
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        try { $line = $serial.ReadLine().Trim() } catch [TimeoutException] { continue }
        if ($line -eq "CFG STATUS_END") { return }
        if ($line.StartsWith("CFG ")) { Write-Host "  $line" }
    }
}

if (-not (Test-Path $TokenFile)) { throw "トークンのファイルがありません：$TokenFile（python -m ct125 register-device --id $DeviceId --token-file $TokenFile）" }
$token = (Get-Content $TokenFile -Raw).Trim()
$password = Read-Secret "Wi-Fi のパスワード（$Ssid）"

$serial = New-Object IO.Ports.SerialPort $Port, 115200
$serial.NewLine = "`n"
$serial.ReadTimeout = 500
$serial.Open()
try {
    Write-Host "ESP32 の起動を待っています（ポートを開くと再起動することがあります）"
    Start-Sleep -Seconds 4
    $serial.DiscardInBuffer()
    Send-Setting $serial "wifi_ssid" $Ssid
    Send-Setting $serial "wifi_pass" $password
    Send-Setting $serial "device_id" $DeviceId
    Send-Setting $serial "device_token" $token
    if ($ApiBase) { Send-Setting $serial "api_base" $ApiBase }
    Write-Host "ESP32 の設定："
    Show-Status $serial
}
finally {
    $serial.Close()
    $password = $null
    $token = $null
}

Remove-Item $TokenFile
Write-Host "トークンのファイルを消しました。BOOT ボタンを 2 秒押すと、記録を閉じて送信を試します。"
