@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "TAG=v3.0.0"
set "RC=0"

git tag -l "%TAG%" | findstr /x "%TAG%" >nul 2>&1
if not errorlevel 1 (
  echo [!] Tag %TAG% already exists locally.
  git tag -l "%TAG%"
  goto end
)

echo [*] Creating baseline tag %TAG% at HEAD...
git tag -a "%TAG%" -m "Baseline release %TAG%"
if errorlevel 1 set "RC=1" & goto end

echo.
echo [+] Created %TAG%
echo     Push it with:  git push origin %TAG%

:end
echo.
if not defined CI pause
endlocal & exit /b %RC%
