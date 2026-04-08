# Creates FinQuanta.lnk on Desktop -> start_finquanta_desktop.bat
# Run: powershell -ExecutionPolicy Bypass -File .\create_desktop_shortcut.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $root "start_finquanta_desktop.bat"
if (-not (Test-Path -LiteralPath $bat)) {
    Write-Error "Missing: $bat"
}

$desk = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desk "FinQuanta.lnk"

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath = $bat
$sc.WorkingDirectory = $root
$sc.Description = "FinQuanta desktop client"
$ico = Join-Path $root "desktop\resources\finquanta.ico"
if (Test-Path -LiteralPath $ico) {
    $sc.IconLocation = "$ico,0"
}
$sc.Save()

Write-Host "Created: $lnkPath"
