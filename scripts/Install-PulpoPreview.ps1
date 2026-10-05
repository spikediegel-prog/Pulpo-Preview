param(
    [ValidateSet('Recommended','Custom')][string]$Mode = 'Recommended',
    [int]$Workers = 2,
    [switch]$ResetSettings,
    [switch]$NoShortcuts
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This package requires Windows.' }
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable.' }
$sourceExe = Join-Path $PSScriptRoot 'pulpo-preview.exe'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $sourceExe -Algorithm SHA256).Hash -ne $manifest.exe_sha256) {
    throw 'Executable does not match the package manifest.'
}
$installRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\PulpoPreview'))
$profileRoot = Join-Path $env:LOCALAPPDATA 'PulpoPreview'
$profile = Join-Path $profileRoot 'evidence-performance.json'
$destination = Join-Path $installRoot 'pulpo-preview.exe'
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
$hadExecutable = Test-Path -LiteralPath $destination
$backup = Join-Path $installRoot ('pulpo-preview.previous-' + [guid]::NewGuid().ToString('N') + '.exe')
if ($hadExecutable) { Copy-Item -LiteralPath $destination -Destination $backup }
try {
    Copy-Item -LiteralPath $sourceExe -Destination $destination
    if ((Get-FileHash -LiteralPath $destination).Hash -ne $manifest.exe_sha256) { throw 'Installed executable mismatch.' }
    # Source/EXE binding changes are accepted only by the new binary's fresh checks.
    if ((Test-Path -LiteralPath $profile) -and -not $ResetSettings -and $Mode -ne 'Custom') {
        & $destination tune --refresh
    } elseif ($Mode -eq 'Custom') {
        & $destination tune --workers $Workers
    } else {
        & $destination tune --recommended
    }
    if ($LASTEXITCODE -ne 0) { throw 'Settings validation failed. Existing profile was retained.' }
} catch {
    if ($hadExecutable) { Copy-Item -LiteralPath $backup -Destination $destination }
    elseif (Test-Path -LiteralPath $destination) { Remove-Item -LiteralPath $destination }
    throw
}
# Program files and user settings live separately. No profile directory is deleted.
if (-not $NoShortcuts) {
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Pulpo Preview'
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $startMenu 'Pulpo Performance Tuning.lnk'))
$shortcut.TargetPath = $destination
$shortcut.Arguments = 'tune'
$shortcut.WorkingDirectory = $installRoot
$shortcut.WindowStyle = 7
$shortcut.Save()
$setup = $shell.CreateShortcut((Join-Path $startMenu 'Pulpo Preview Setup.lnk'))
$setup.TargetPath = $destination
$setup.WorkingDirectory = $installRoot
$setup.Save()
}
Write-Output "Installed: $destination"
Write-Output "Settings retained at: $profile"
Write-Output 'Open Pulpo Performance Tuning from the Start menu.'
if ($hadExecutable) { Write-Output "Previous executable retained: $backup" }
