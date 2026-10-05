param(
    [ValidateSet('PTC', 'Regression')][string]$Suite = 'Regression',
    [string]$Python,
    [string]$LogPath,
    [switch]$Pause
)

$ErrorActionPreference = 'Stop'
$repoDirectory = Split-Path -Parent $PSScriptRoot
$testExitCode = 1
try {
    if (-not $Python) {
        $candidates = @()
        foreach ($commandName in @('python', 'python3')) {
            $commandInfo = Get-Command $commandName -ErrorAction SilentlyContinue
            if ($commandInfo) { $candidates += $commandInfo.Source }
        }
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            try {
                $resolvedPython = & $launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { $candidates += $resolvedPython }
            } catch { }
        }
        $bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
        if (Test-Path -LiteralPath $bundledPython) { $candidates += $bundledPython }
        foreach ($candidate in $candidates) {
            try {
                & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
                if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
            } catch { }
        }
    }
    if (-not $Python) { throw 'Python 3.11 or newer was not found. Pass -Python with its full path.' }
    $modules = @('tests.test_traffic')
    if ($Suite -eq 'Regression') {
        $modules += @('tests.test_kernel', 'tests.test_directives', 'tests.test_orchestrator',
            'tests.test_execution_context_binding', 'tests.test_audit_checkpoint',
            'tests.test_persistence', 'tests.test_authority', 'tests.test_custody_executor')
    }
    Write-Host "Running $Suite tests in $repoDirectory"
    $runnerCode = 'import sys, unittest; result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])); sys.exit(not result.wasSuccessful())'
    Push-Location -LiteralPath $repoDirectory
    try {
        # Send ordinary test progress to stdout for clean logs on PowerShell 5/7.
        # Preserve the test runner's real exit code.
        $ErrorActionPreference = 'Continue'
        if ($LogPath) {
            & $Python -c $runnerCode @modules 2>&1 | Tee-Object -FilePath $LogPath
        } else {
            & $Python -c $runnerCode @modules
        }
        $testExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($testExitCode -eq 0) { Write-Host 'All selected tests passed.' -ForegroundColor Green }
    else { Write-Host "Tests failed (exit code $testExitCode). Review the output above." -ForegroundColor Red }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    if ($Pause) { Read-Host 'Press Enter to close' | Out-Null }
}
exit $testExitCode
