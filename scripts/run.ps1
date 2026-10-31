$ErrorActionPreference = "Stop"

$pythonPath = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = "python"
}

& $pythonPath (Join-Path $PSScriptRoot "..\bot.py")
