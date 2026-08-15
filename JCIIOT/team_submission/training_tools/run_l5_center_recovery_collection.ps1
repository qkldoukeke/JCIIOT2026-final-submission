$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $PSScriptRoot "..\resolve_python.ps1")
$pythonExe = Get-JciPython
$collectorPath = Join-Path $PSScriptRoot "collect_factory_sorting.py"
$outputRoot = Join-Path $projectRoot "team_submission\training_data_raw\l5_recovery_formal"
$logRoot = Join-Path $projectRoot "team_submission\training_runs"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logRoot "l5_center_recovery_collection_$stamp.log"

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
Set-Location -LiteralPath $projectRoot

function Invoke-RecoveryGroup {
    param(
        [Parameter(Mandatory = $true)][double]$JointJitter,
        [Parameter(Mandatory = $true)][int]$Seed,
        [Parameter(Mandatory = $true)][string]$OutputName
    )

    & $pythonExe -u $collectorPath `
        --level L5 `
        --object-index 0 `
        --num-rollouts 25 `
        --clean-rollouts 0 `
        --base-xy-jitter 0 `
        --object-xy-jitter 0 `
        --arm-joint-jitter $JointJitter `
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

Start-Transcript -LiteralPath $logPath
try {
    Invoke-RecoveryGroup -JointJitter 0.01 -Seed 15911 `
        -OutputName "l5_center_arm_recovery_001"
    Invoke-RecoveryGroup -JointJitter 0.02 -Seed 15912 `
        -OutputName "l5_center_arm_recovery_002"
}
finally {
    Stop-Transcript
}
