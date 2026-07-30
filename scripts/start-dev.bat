@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "RC=0"

where uv >nul 2>&1
if errorlevel 1 (
  echo [!] uv not found — run scripts\install-uv.bat first.
  set "RC=1"
  goto end
)

echo [*] Syncing dependencies...
uv sync
if errorlevel 1 (
  set "RC=1"
  goto end
)

echo [*] Starting WareStore (dev)...
uv run warestore
if errorlevel 1 set "RC=1"

:end
if %RC% neq 0 (
  echo.
  pause
)
endlocal & exit /b %RC%
