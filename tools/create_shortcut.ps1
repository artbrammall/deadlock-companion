param([Parameter(Mandatory=$true)][string]$Executable)
$ErrorActionPreference = 'Stop'
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$desktopFolder = [Environment]::GetFolderPath('Desktop')
$shellObject = New-Object -ComObject WScript.Shell
$link = $shellObject.CreateShortcut((Join-Path $desktopFolder 'Deadlock Foresight.lnk'))
$link.TargetPath = $resolvedExecutable
$link.WorkingDirectory = Split-Path -Parent $resolvedExecutable
$link.IconLocation = "$resolvedExecutable,0"
$link.Description = 'Hero recommendations for Deadlock'
$link.Save()
Write-Output "Desktop shortcut created: $desktopFolder\Deadlock Foresight.lnk"
