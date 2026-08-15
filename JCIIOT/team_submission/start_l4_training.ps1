$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "resolve_python.ps1")
$pythonExe = Get-JciPython
$launcher = Join-Path $PSScriptRoot "launch_l4_training.py"
& $pythonExe $launcher
