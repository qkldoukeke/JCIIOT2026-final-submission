function Get-JciPython {
    if ($env:JCI_PYTHON) {
        if (-not (Test-Path -LiteralPath $env:JCI_PYTHON)) {
            throw "JCI_PYTHON does not exist: $env:JCI_PYTHON"
        }
        return (Resolve-Path -LiteralPath $env:JCI_PYTHON).Path
    }

    if ($env:CONDA_PREFIX) {
        $condaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path -LiteralPath $condaPython) {
            return (Resolve-Path -LiteralPath $condaPython).Path
        }
    }

    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Python was not found. Activate the jciiot environment or set JCI_PYTHON."
    }
    return $command.Source
}
