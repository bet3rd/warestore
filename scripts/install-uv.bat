@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "RC=0"

where uv >nul 2>&1
if not errorlevel 1 (
  echo [*] uv is already installed:
  uv --version
  goto end
)

echo [*] Installing uv (official installer)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 (
  echo [!] uv install failed.
  set "RC=1"
  goto end
)

where uv >nul 2>&1
if errorlevel 1 (
  echo.
  echo [!] uv was installed but is not on PATH in this shell.
  echo     Close and reopen the terminal, or add %%USERPROFILE%%\.local\bin to PATH.
  set "RC=1"
  goto end
)

echo.
echo [+] uv installed:
uv --version

:end
echo.
pause
endlocal & exit /b %RC%
