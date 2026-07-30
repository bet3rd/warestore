@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "RC=0"

echo [*] Syncing dev dependencies...
uv sync --group dev
if errorlevel 1 set "RC=1" & goto end

echo [*] Running tests...
uv run pytest %*
if errorlevel 1 set "RC=1"

:end
echo.
pause
endlocal & exit /b %RC%
