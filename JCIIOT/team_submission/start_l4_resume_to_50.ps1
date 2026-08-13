$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configPath = Join-Path $PSScriptRoot "training_configs\factory_sorting_l4_upper_bc_resume_to_50.json"

Set-Location $projectRoot
& "D:\tool\anaconda3\envs\jci_clean\python.exe" -u -m robomimic.scripts.train --config $configPath --resume

if ($LASTEXITCODE -ne 0) {
    throw "L4 resume training failed with exit code $LASTEXITCODE"
}
