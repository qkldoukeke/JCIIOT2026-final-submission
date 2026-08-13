$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pythonExe = "D:\tool\anaconda3\envs\jci_clean\python.exe"
$collectorPath = Join-Path $projectRoot "team_submission\training_tools\collect_factory_sorting.py"
$outputRoot = Join-Path $projectRoot "team_submission\training_data_raw\l3_formal"
$runLogRoot = Join-Path $projectRoot "team_submission\training_runs"
$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$transcriptPath = Join-Path $runLogRoot "l3_formal_collection_$runStamp.log"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $runLogRoot -Force | Out-Null
Set-Location $projectRoot

function Invoke-L3CollectionGroup {
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
        --level L3 `
        --object-index $ObjectIndex `
        --num-rollouts $Rollouts `
        --clean-rollouts $CleanRollouts `
        --base-xy-jitter $BaseJitter `
        --object-xy-jitter $ObjectJitter `
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
    Invoke-L3CollectionGroup -ObjectIndex 0 -Rollouts 25 -CleanRollouts 25 `
        -BaseJitter 0.0 -ObjectJitter 0.0 -Seed 13101 `
        -OutputName "l3_far_right_clean"
    Invoke-L3CollectionGroup -ObjectIndex 0 -Rollouts 50 -CleanRollouts 0 `
        -BaseJitter 0.02 -ObjectJitter 0.0 -Seed 13102 `
        -OutputName "l3_far_right_base_jitter"
    Invoke-L3CollectionGroup -ObjectIndex 0 -Rollouts 25 -CleanRollouts 0 `
        -BaseJitter 0.0 -ObjectJitter 0.01 -Seed 13103 `
        -OutputName "l3_far_right_object_jitter"

    Invoke-L3CollectionGroup -ObjectIndex 1 -Rollouts 25 -CleanRollouts 25 `
        -BaseJitter 0.0 -ObjectJitter 0.0 -Seed 13201 `
        -OutputName "l3_near_right_clean"
    Invoke-L3CollectionGroup -ObjectIndex 1 -Rollouts 50 -CleanRollouts 0 `
        -BaseJitter 0.02 -ObjectJitter 0.0 -Seed 13202 `
        -OutputName "l3_near_right_base_jitter"
    Invoke-L3CollectionGroup -ObjectIndex 1 -Rollouts 25 -CleanRollouts 0 `
        -BaseJitter 0.0 -ObjectJitter 0.01 -Seed 13203 `
        -OutputName "l3_near_right_object_jitter"

    Write-Host ""
    Write-Host "L3 formal collection completed."
    Write-Host "Output root: $outputRoot"
}
finally {
    Stop-Transcript
}
