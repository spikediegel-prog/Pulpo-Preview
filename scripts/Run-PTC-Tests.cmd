@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-PTC-Tests.ps1" -Pause
exit /b %ERRORLEVEL%
