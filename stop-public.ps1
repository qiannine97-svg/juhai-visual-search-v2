$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "public-pids.txt"

if (-not (Test-Path -LiteralPath $PidFile)) {
  Write-Output "No public test process record found."
  exit 0
}

Get-Content -LiteralPath $PidFile | ForEach-Object {
  $Parts = $_ -split "=", 2
  if ($Parts.Count -eq 2 -and $Parts[1] -match "^\d+$") {
    Stop-Process -Id ([int]$Parts[1]) -Force -ErrorAction SilentlyContinue
  }
}

Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
Write-Output "Stopped."
