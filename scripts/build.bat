@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "ROOT=%CD%"
set "ICON=%ROOT%\assets\warestore.ico"
set "OUT=%ROOT%\dist"
set "ENTRY=%ROOT%\src\warestore\presentation\account_manager\main.py"
set "RC=0"

echo [*] Ensuring app icon exists...
uv run python -c "from warestore.presentation.account_manager.ui.theme import ensure_app_icon_file; ensure_app_icon_file()"
if errorlevel 1 set "RC=1" & goto end

echo [*] Syncing dev dependencies...
uv sync --group dev
if errorlevel 1 set "RC=1" & goto end

echo [*] Cleaning previous build artifacts...
if exist "%ROOT%\build" rmdir /s /q "%ROOT%\build"
if exist "%OUT%\WareStore.exe" del /f /q "%OUT%\WareStore.exe"
if exist "%OUT%\WareStoreSetup.exe" del /f /q "%OUT%\WareStoreSetup.exe"
if exist "%OUT%\exe" rmdir /s /q "%OUT%\exe"
if exist "%OUT%\WareStore" rmdir /s /q "%OUT%\WareStore"

echo [*] Building app folder (onedir)...
uv run pyinstaller ^
  --noconfirm ^
  --distpath "%OUT%" ^
  --workpath "%ROOT%\build\pyi-work" ^
  "%ROOT%\warestore.spec"
if errorlevel 1 set "RC=1" & goto end

echo [*] Removing build dir...
if exist "%ROOT%\build" rmdir /s /q "%ROOT%\build"

if not exist "%OUT%\WareStore\WareStore.exe" (
  echo [!] Build failed — WareStore\WareStore.exe not found.
  set "RC=1" & goto end
)

echo [*] Locating Inno Setup compiler (ISCC)...
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo [!] ISCC.exe not found. Install Inno Setup 6: winget install JRSoftware.InnoSetup
  echo [!] The onedir folder is at %OUT%\WareStore — installer not built.
  set "RC=1" & goto end
)

echo [*] Reading app version...
set "APPVER="
for /f "usebackq delims=" %%V in (`uv run python -c "from warestore import __version__; print(__version__)"`) do set "APPVER=%%V"
if not defined APPVER set "APPVER=0.0"

echo [*] Compiling installer (v%APPVER%)...
"%ISCC%" /DMyAppVersion=%APPVER% "%ROOT%\installer\warestore.iss"
if errorlevel 1 set "RC=1" & goto end

echo.
if exist "%OUT%\WareStoreSetup.exe" (
  echo Built: %OUT%\WareStoreSetup.exe  ^(installs to Program Files\WareStore^)
) else (
  echo [!] Installer compile failed — WareStoreSetup.exe not found.
  set "RC=1"
)

:end
echo.
if not defined CI pause
endlocal & exit /b %RC%
