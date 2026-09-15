$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cloudflared = Resolve-Path (Join-Path $Root "..\tools\cloudflared.exe")
$Port = "4192"

$ServerLog = Join-Path $Root "public-server.log"
$ServerErr = Join-Path $Root "public-server.err.log"
$TunnelOut = Join-Path $Root "public-tunnel.out.log"
$TunnelErr = Join-Path $Root "public-tunnel.err.log"
$PidFile = Join-Path $Root "public-pids.txt"
$UrlFile = Join-Path $Root "public-url.txt"

function Read-SharedText($Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return ""
  }
  $Stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
  try {
    $Reader = New-Object IO.StreamReader($Stream)
    try {
      return $Reader.ReadToEnd()
    } finally {
      $Reader.Dispose()
    }
  } finally {
    $Stream.Dispose()
  }
}

Remove-Item -LiteralPath $ServerLog, $ServerErr, $TunnelOut, $TunnelErr, $PidFile, $UrlFile -ErrorAction SilentlyContinue

$Server = Start-Process `
  -FilePath "powershell" `
  -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "`$env:PORT='$Port'; python server.py" `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $ServerLog `
  -RedirectStandardError $ServerErr `
  -PassThru

$Deadline = (Get-Date).AddSeconds(30)
do {
  Start-Sleep -Milliseconds 300
  $Ok = $false
  try {
    $Ok = (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 4).StatusCode -eq 200
  } catch {}
} while (-not $Ok -and (Get-Date) -lt $Deadline)

if (-not $Ok) {
  Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
  throw "Local server failed to start."
}

$Tunnel = Start-Process `
  -FilePath $Cloudflared `
  -ArgumentList "tunnel", "--url", "http://localhost:$Port" `
  -WorkingDirectory $Root `
  -WindowStyle Hidden `
  -RedirectStandardOutput $TunnelOut `
  -RedirectStandardError $TunnelErr `
  -PassThru

$Url = $null
$Deadline = (Get-Date).AddSeconds(35)
do {
  Start-Sleep -Milliseconds 500
  $Logs = ""
  foreach ($Log in @($TunnelOut, $TunnelErr)) {
    $Logs += Read-SharedText $Log
  }
  $Match = [regex]::Match($Logs, "https://[a-z0-9-]+\.trycloudflare\.com")
  if ($Match.Success) {
    $Url = $Match.Value
  }
} while (-not $Url -and (Get-Date) -lt $Deadline)

if (-not $Url) {
  Stop-Process -Id $Tunnel.Id -Force -ErrorAction SilentlyContinue
  Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
  throw "Public tunnel failed to start."
}

Set-Content -LiteralPath $UrlFile -Value $Url -Encoding UTF8
Set-Content -LiteralPath $PidFile -Value @("server=$($Server.Id)", "tunnel=$($Tunnel.Id)") -Encoding ASCII
Write-Output $Url
