param([string]$Python = "python")
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Build the Windows executable on Windows." }
$repoRoot = Split-Path $PSScriptRoot -Parent
$buildRoot = Join-Path $repoRoot "work/windows-exe-build"
& $Python -m venv $buildRoot
if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
$buildPython = Join-Path $buildRoot "Scripts/python.exe"
& $buildPython -m pip install -r (Join-Path $PSScriptRoot "requirements-windows-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Could not install build requirements." }
& $buildPython -m PyInstaller --noconfirm --clean --onefile --console --noupx --name pulpo-preview --paths $repoRoot --distpath (Join-Path $repoRoot "dist/windows-preview") --workpath (Join-Path $repoRoot "build/windows-preview") --specpath (Join-Path $repoRoot "build") (Join-Path $PSScriptRoot "windows_launcher.py")
if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
Write-Output "Built: $repoRoot/dist/windows-preview/pulpo-preview.exe"
