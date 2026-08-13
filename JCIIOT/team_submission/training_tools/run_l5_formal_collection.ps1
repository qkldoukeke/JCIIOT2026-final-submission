$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonExe = "D:\tool\anaconda3\envs\jci_clean\python.exe"
$collectorPath = Join-Path $PSScriptRoot "collect_factory_sorting.py"
$outputRoot = Join-Path $projectRoot "team_submission\training_data_raw\l5_formal"
$runLogRoot = Join-Path $projectRoot "team_submission\training_runs"
$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$transcriptPath = Join-Path $runLogRoot "l5_formal_collection_$runStamp.log"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runLogRoot -Force | Out-Null
Set-Location -LiteralPath $projectRoot

function Invoke-L5CollectionGroup {
    param(
        [Parameter(Mandatory = $true)][int]$ObjectIndex,
        [Parameter(Mandatory = $true)][int]$Rollouts,
        [Parameter(Mandatory = $true)][int]$CleanRollouts,
        [Parameter(Mandatory = $true)][double]$BaseJitter,
        [Parameter(Mandatory = $true)][double]$ObjectJitter,
        [Parameter(Mandatory = $true)][int]$Seed,
        [Parameter(Mandatory = $true)][string]$OutputName
    )

    Write-Host ""
    Write-Host "Starting $OutputName"
    & $pythonExe -u $collectorPath `
        --level L5 `
        --object-index $ObjectIndex `
        --num-rollouts $Rollouts `
        --clean-rollouts $CleanRollouts `
        --base-xy-jitter $BaseJitter `
        --object-xy-jitter $ObjectJitter `
        --max-object-horizontal-drift 0.04 `
        --max-object-linear-speed 0.05 `
        --no-render `
        --seed $Seed `
        --directory $outputRoot `
        --output-name $OutputName

    if ($LASTEXITCODE -ne 0) {
        throw "$OutputName failed with exit code $LASTEXITCODE"
    }
}

$objects = @(
    @{ Index = 0; Name = "center"; SeedBase = 15100 },
    @{ Index = 1; Name = "front";  SeedBase = 15200 },
    @{ Index = 2; Name = "back";   SeedBase = 15300 }
)

Start-Transcript -LiteralPath $transcriptPath
try {
    foreach ($object in $objects) {
        Invoke-L5CollectionGroup -ObjectIndex $object.Index -Rollouts 25 `
            -CleanRollouts 25 -BaseJitter 0.0 -ObjectJitter 0.0 `
            -Seed ($object.SeedBase + 1) `
            -OutputName "l5_$($object.Name)_clean"
        Invoke-L5CollectionGroup -ObjectIndex $object.Index -Rollouts 50 `
            -CleanRollouts 0 -BaseJitter 0.02 -ObjectJitter 0.0 `
            -Seed ($object.SeedBase + 2) `
            -OutputName "l5_$($object.Name)_base_jitter"
        Invoke-L5CollectionGroup -ObjectIndex $object.Index -Rollouts 25 `
            -CleanRollouts 0 -BaseJitter 0.0 -ObjectJitter 0.01 `
            -Seed ($object.SeedBase + 3) `
            -OutputName "l5_$($object.Name)_object_jitter"
    }

    Write-Host ""
    Write-Host "L5 formal collection completed."
    Write-Host "Output root: $outputRoot"
}
finally {
    Stop-Transcript
}
