. (Join-Path $PSScriptRoot "resolve_python.ps1")
$pythonExe = Get-JciPython
$launcher = Join-Path $PSScriptRoot "launch_l3_resume_training.py"
& $pythonExe $launcher
