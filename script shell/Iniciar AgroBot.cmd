@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1" %*
set "VETRA_EXIT_CODE=%ERRORLEVEL%"
if not "%VETRA_EXIT_CODE%"=="0" pause
exit /b %VETRA_EXIT_CODE%
