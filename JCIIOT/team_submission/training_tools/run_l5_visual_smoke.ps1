$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot "..\resolve_python.ps1")
$pythonExe = Get-JciPython
$collectorPath = Join-Path $PSScriptRoot "collect_factory_sorting.py"
$outputRoot = Join-Path $projectRoot "team_submission\training_data_raw\l5_visual_smoke"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
Set-Location -LiteralPath $projectRoot

$objects = @(
    @{ Index = 0; Name = "center"; Seed = 15200 },
    @{ Index = 1; Name = "front";  Seed = 15201 },
    @{ Index = 2; Name = "back";   Seed = 15202 }
)

foreach ($object in $objects) {
    Write-Host ""
    Write-Host "L5 visual grasp: $($object.Name) object (index $($object.Index))"
    & $pythonExe -u $collectorPath `
        --level L5 `
        --object-index $object.Index `
        --num-rollouts 1 `
        --clean-rollouts 1 `
        --show-object-sites `
        --render-sleep 0.01 `
        --seed $object.Seed `
        --directory $outputRoot `
        --output-name "l5_$($object.Name)_visual_smoke"

    if ($LASTEXITCODE -ne 0) {
        throw "L5 $($object.Name) visual grasp failed with exit code $LASTEXITCODE"
    }
}

Write-Host ""
Write-Host "L5 center, front, and back visual grasp checks completed."
