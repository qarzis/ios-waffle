@echo off
setlocal EnableExtensions
pushd "%~dp0"
set "PYTHONUTF8=1"
set "CMD=%~1"
if "%CMD%"=="" goto help
if /i "%CMD%"=="-h" goto help
if /i "%CMD%"=="--help" goto help
for %%c in (--get --boot --run --fetch --assemble --firmware --wifi --android --status --tools --driver) do if /i "%CMD%"=="%%c" goto native
for %%c in (--install --deps --build --kernel --clean) do if /i "%CMD%"=="%%c" goto linux
echo hackios: unknown command %CMD%
goto help

:native
call :python || goto fail
if /i "%CMD%"=="--get" (call :sevenzip || goto fail)
if /i "%CMD%"=="--fetch" (call :sevenzip || goto fail)
"%PY%" scripts\hackios_tool.py %*
set "RC=%ERRORLEVEL%"
popd & exit /b %RC%

:linux
call :wsl || goto fail
wsl --cd "%LINUXDIR%" -e bash ./hackios %*
set "RC=%ERRORLEVEL%"
popd & exit /b %RC%

:python
set "BASEPY="
where py >nul 2>nul && set "BASEPY=py -3"
if not defined BASEPY (
  python -c "import sys" >nul 2>nul && set "BASEPY=python"
)
if not defined BASEPY (
  echo hackios: Python 3 is not installed.
  echo hackios: install it with:  winget install -e --id Python.Python.3.12
  echo hackios: or from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^), then run this again.
  exit /b 1
)
set "PY=%CD%\work\pyenv\Scripts\python.exe"
if exist "%PY%" exit /b 0
echo hackios: preparing Python ^(once^)
if not exist work mkdir work
%BASEPY% -m venv work\pyenv || exit /b 1
"%PY%" -m pip install -q zstandard || exit /b 1
exit /b 0

:sevenzip
where 7z >nul 2>nul && exit /b 0
if exist "C:\Program Files\7-Zip\7z.exe" exit /b 0
echo hackios: 7-Zip is needed to unpack iOS; installing it with winget...
winget install -e --id 7zip.7zip --accept-source-agreements --accept-package-agreements
if exist "C:\Program Files\7-Zip\7z.exe" exit /b 0
echo hackios: install 7-Zip from https://www.7-zip.org/ and run this again.
exit /b 1

:wsl
where wsl >nul 2>nul || (
  echo hackios: building everything yourself needs WSL 2 with Ubuntu: wsl --install -d Ubuntu
  echo hackios: you do not need it for --get and --boot.
  exit /b 1
)
set "LINUXDIR="
for /f "usebackq delims=" %%p in (`wsl -e wslpath -a "%~dp0."`) do set "LINUXDIR=%%p"
if not defined LINUXDIR (
  echo hackios: WSL has no Linux distribution: wsl --install -d Ubuntu
  exit /b 1
)
exit /b 0

:help
echo.
echo   HackiOS for the OnePlus Ace 6T - Windows 10 / 11
echo.
echo   hackios.bat --wifi NAME PASS    the Wi-Fi network iOS joins
echo   hackios.bat --get               download everything: the release, iOS from Apple, the phone's firmware
echo   hackios.bat --boot              start iOS on the phone
echo   hackios.bat --boot -- --island 2    ... with options after --
echo   hackios.bat --android           back to Android
echo   hackios.bat --status            what is connected and what is ready
echo   hackios.bat --driver            the USB driver, if Windows does not see the phone in fastboot
echo.
echo   single steps: --fetch  --firmware  --assemble  --run  --tools ^(adb and fastboot^)
echo   building everything yourself ^(needs WSL^): --install  --build
echo.
popd & exit /b 0

:fail
echo hackios: stopped.
popd & exit /b 1
