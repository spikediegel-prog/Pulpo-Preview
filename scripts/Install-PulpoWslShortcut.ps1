param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')][string]$Distribution = 'Ubuntu',
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^/[A-Za-z0-9_./-]+$')][string]$Checkout
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Run this installer on Windows.' }
if ($Checkout -eq '/' -or $Checkout.Split('/') -contains '..') {
    throw 'Choose an absolute WSL checkout path without parent traversal.'
}
$Checkout = $Checkout.TrimEnd('/')
$wsl = Join-Path $env:SystemRoot 'System32\wsl.exe'
$launcher = "$Checkout/.venv/bin/pulpo"
& $wsl -d $Distribution -- /usr/bin/test -x $launcher
if ($LASTEXITCODE -ne 0) { throw 'The existing WSL Pulpo executable was not found.' }
$programs = [Environment]::GetFolderPath('Programs')
if (-not $programs) { throw 'The current user Start menu is unavailable.' }
$folder = Join-Path $programs 'Pulpo Preview'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$path = Join-Path $folder 'Pulpo Control Center (WSL).lnk'
# Updating this named launcher never replaces the separate Windows shortcuts.
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($path)
$shortcut.TargetPath = $wsl
$shortcut.Arguments = "-d $Distribution --cd $Checkout -- $launcher tune"
$shortcut.Description = 'Open the existing WSL Pulpo Control Center. No workload or export producer is started.'
$shortcut.WindowStyle = 7
$shortcut.Save()
$saved = $shell.CreateShortcut($path)
if ($saved.TargetPath -ne $wsl -or $saved.Arguments -ne $shortcut.Arguments) {
    throw 'Shortcut verification failed.'
}
Write-Output "Installed: $path"
Write-Output 'Search Start for Pulpo Control Center (WSL).'
