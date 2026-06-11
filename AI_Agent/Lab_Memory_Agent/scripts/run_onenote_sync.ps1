$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = $env:ZZLAB_PYTHON
if (-not $Python) {
    $CodexPython = "C:\Users\ustcr\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $CodexPython) {
        $Python = $CodexPython
    } else {
        $Python = "python"
    }
}

$LogDir = Join-Path $Root "logs\onenote_sync"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "$Stamp.log"

Start-Transcript -Path $LogFile -Force | Out-Null
try {
    Set-Location $Root
    & $Python -m pip show msal
    if ($LASTEXITCODE -ne 0) {
        throw "Python package 'msal' is missing. Install it with: $Python -m pip install msal"
    }

    & $Python ".\scripts\sync_onenote_graph.py"
    if ($LASTEXITCODE -ne 0) { throw "sync_onenote_graph.py failed with exit code $LASTEXITCODE" }

    & $Python ".\scripts\rebuild_index.py"
    if ($LASTEXITCODE -ne 0) { throw "rebuild_index.py failed with exit code $LASTEXITCODE" }
}
finally {
    Stop-Transcript | Out-Null
}
