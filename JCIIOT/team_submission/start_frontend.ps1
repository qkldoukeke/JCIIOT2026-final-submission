$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $PSScriptRoot "launch_with_local_api.py"

Set-Location -LiteralPath $projectRoot

$pythonExe = $null

# Optional explicit override for machines whose environment is not activated.
if ($env:JCI_PYTHON -and (Test-Path -LiteralPath $env:JCI_PYTHON)) {
    $pythonExe = (Resolve-Path -LiteralPath $env:JCI_PYTHON).Path
}

# Portable path: activate jciiot first, then this resolves on another PC.
if (-not $pythonExe -and $env:CONDA_PREFIX) {
    $condaPython = Join-Path $env:CONDA_PREFIX "python.exe"
    if (Test-Path -LiteralPath $condaPython) {
        $pythonExe = (Resolve-Path -LiteralPath $condaPython).Path
    }
}

# Final fallback for a correctly configured PATH.
if (-not $pythonExe) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonExe = $pythonCommand.Source
    }
}

if (-not $pythonExe) {
    throw "Python not found. Activate the jciiot environment first, or set JCI_PYTHON to its python.exe."
}

Write-Host "Frontend Python: $pythonExe"
& $pythonExe -m streamlit run $launcher
