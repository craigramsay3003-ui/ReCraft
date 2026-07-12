@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_release.ps1"
set "BUILD_EXIT=%ERRORLEVEL%"
echo.
if not "%BUILD_EXIT%"=="0" echo ReCraft build failed with exit code %BUILD_EXIT%.
pause
exit /b %BUILD_EXIT%
