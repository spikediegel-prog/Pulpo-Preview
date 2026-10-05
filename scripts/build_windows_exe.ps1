param([string]$Python = "python", [switch]$SkipDependencyInstall)
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Build the Windows executable on Windows." }
$repoRoot = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $repoRoot "work/windows-exe-build"
$buildPython = Join-Path $buildRoot "Scripts/python.exe"
if (-not (Test-Path -LiteralPath $buildPython)) {
    & $Python -m venv $buildRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
}
if (-not $SkipDependencyInstall) {
    & $buildPython -m pip install -r (Join-Path $PSScriptRoot "requirements-windows-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install build requirements." }
}
& $buildPython -c "import tkinter; tkinter.Tcl()"
if ($LASTEXITCODE -ne 0) { throw "Build Python requires Tcl/Tk for the tuning app." }
$packageRoot = Join-Path $repoRoot 'dist/windows-tuning-preview'
& $buildPython -m PyInstaller --noconfirm --clean --onefile --console --noupx --name pulpo-preview --hidden-import pulpo.tuning_app --hidden-import tkinter --paths $repoRoot --distpath $packageRoot --workpath (Join-Path $repoRoot "build/windows-tuning-preview") --specpath (Join-Path $repoRoot "build") (Join-Path $PSScriptRoot "windows_launcher.py")
if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
$exe = Join-Path $packageRoot 'pulpo-preview.exe'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Install-PulpoPreview.ps1') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $repoRoot 'docs/WINDOWS_TUNING_PACKAGE.md') -Destination (Join-Path $packageRoot 'README.md')
$manifest = @{
    schema='pulpo.windows-tuning-package.v1'
    classification='Recorded build; operator smoke tests pending'
    exe_sha256=(Get-FileHash -LiteralPath $exe).Hash
    installer_sha256=(Get-FileHash -LiteralPath (Join-Path $packageRoot 'Install-PulpoPreview.ps1')).Hash
    built_utc=[DateTime]::UtcNow.ToString('o')
    authority_effect='none'
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $packageRoot 'manifest.json') -Encoding utf8
$zip = Join-Path $repoRoot 'dist/pulpo-preview-tuning-windows.zip'
Compress-Archive -LiteralPath @($exe,(Join-Path $packageRoot 'Install-PulpoPreview.ps1'),(Join-Path $packageRoot 'README.md'),(Join-Path $packageRoot 'manifest.json')) -DestinationPath $zip -Force
Write-Output "Built package: $zip"
