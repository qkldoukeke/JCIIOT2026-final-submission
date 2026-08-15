$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $PSScriptRoot "training_configs\factory_sorting_l4_upper_bc_resume_to_50.json"
. (Join-Path $PSScriptRoot "resolve_python.ps1")
$pythonExe = Get-JciPython

Set-Location $projectRoot
& $pythonExe -u -m robomimic.scripts.train --config $configPath --resume

if ($LASTEXITCODE -ne 0) {
    throw "L4 resume training failed with exit code $LASTEXITCODE"
}
