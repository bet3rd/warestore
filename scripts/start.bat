@echo off
setlocal
cd /d "%~dp0.."

set "EXE=%CD%\dist\WareStore.exe"
if not exist "%EXE%" (
  echo [!] WareStore.exe not found — run scripts\build.bat first.
  echo.
  pause
  exit /b 1
)

start "" "%EXE%"
endlocal
