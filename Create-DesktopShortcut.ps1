param(
    [string]$DestinationDirectory = [Environment]::GetFolderPath('DesktopDirectory')
)

$ErrorActionPreference = 'Stop'
$projectDirectory = $PSScriptRoot
$pythonPath = Join-Path $projectDirectory '.venv\Scripts\pythonw.exe'
$settingsPath = Join-Path $projectDirectory 'settings.py'
$iconPath = Join-Path $projectDirectory 'assets\app-icon.ico'
foreach ($requiredPath in @($pythonPath, $settingsPath, $iconPath, $DestinationDirectory)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path does not exist: $requiredPath"
    }
}

$shortcutPath = Join-Path $DestinationDirectory 'AMD HUD.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonPath
$shortcut.Arguments = '"' + $settingsPath + '"'
$shortcut.WorkingDirectory = $projectDirectory
$shortcut.IconLocation = $iconPath + ',0'
$shortcut.Description = 'Configure AMD HUD appearance and behavior'
$shortcut.Save()
Write-Output "Updated desktop shortcut: $shortcutPath"
