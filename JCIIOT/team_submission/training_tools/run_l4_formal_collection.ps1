$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot "..\resolve_python.ps1")
$pythonExe = Get-JciPython
$collectorPath = Join-Path $projectRoot "team_submission\training_tools\collect_factory_sorting.py"
$outputRoot = Join-Path $projectRoot "team_submission\training_data_raw\l4_formal"
$runLogRoot = Join-Path $projectRoot "team_submission\training_runs"
$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$transcriptPath = Join-Path $runLogRoot "l4_formal_collection_$runStamp.log"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runLogRoot -Force | Out-Null
Set-Location $projectRoot

function Invoke-L4CollectionGroup {
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
    & $pythonExe $collectorPath `
        --level L4 `
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

Start-Transcript -LiteralPath $transcriptPath
try {
    Invoke-L4CollectionGroup -ObjectIndex 0 -Rollouts 25 -CleanRollouts 25 `
        -BaseJitter 0.0 -ObjectJitter 0.0 -Seed 14101 `
        -OutputName "l4_upper_clean"
    Invoke-L4CollectionGroup -ObjectIndex 0 -Rollouts 50 -CleanRollouts 0 `
        -BaseJitter 0.02 -ObjectJitter 0.0 -Seed 14102 `
        -OutputName "l4_upper_base_jitter"
    Invoke-L4CollectionGroup -ObjectIndex 0 -Rollouts 25 -CleanRollouts 0 `
        -BaseJitter 0.0 -ObjectJitter 0.01 -Seed 14103 `
        -OutputName "l4_upper_object_jitter"

    Invoke-L4CollectionGroup -ObjectIndex 1 -Rollouts 25 -CleanRollouts 25 `
        -BaseJitter 0.0 -ObjectJitter 0.0 -Seed 14201 `
        -OutputName "l4_lower_clean"
    Invoke-L4CollectionGroup -ObjectIndex 1 -Rollouts 50 -CleanRollouts 0 `
        -BaseJitter 0.02 -ObjectJitter 0.0 -Seed 14202 `
        -OutputName "l4_lower_base_jitter"
    Invoke-L4CollectionGroup -ObjectIndex 1 -Rollouts 25 -CleanRollouts 0 `
        -BaseJitter 0.0 -ObjectJitter 0.01 -Seed 14203 `
        -OutputName "l4_lower_object_jitter"

    Write-Host ""
    Write-Host "L4 formal collection completed."
    Write-Host "Output root: $outputRoot"
}
finally {
    Stop-Transcript
}
