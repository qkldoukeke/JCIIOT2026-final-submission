$ErrorActionPreference = "Stop"

$launcher = Join-Path $PSScriptRoot "launch_l1_training.py"
& "D:\tool\anaconda3\envs\jci_clean\python.exe" $launcher @args
