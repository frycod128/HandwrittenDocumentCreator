@echo off
rem One-click launcher for the A3 handwriting document generator.
rem It only prepares files inside this project: no global installs,
rem no PATH or registry changes.
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
set "PYARGS="

if exist ".python\python.exe" (
    ".python\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=.python\python.exe"
)

if not defined PY if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=.venv\Scripts\python.exe"
)

if not defined PY (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "PY=py.exe"
        set "PYARGS=-3"
    )
)

if not defined PY (
    python.exe -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python.exe"
)

if not defined PY (
    python3.exe -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python3.exe"
)

if defined PY goto run

echo [setup] No usable Python found on this computer.
echo [setup] Downloading a project-local Python into .python ...
powershell -NoProfile -ExecutionPolicy Bypass -File "tools\get_python.ps1"
if errorlevel 1 goto fail
if not exist ".python\python.exe" goto fail
set "PY=.python\python.exe"

:run
"%PY%" %PYARGS% "tools\bootstrap.py" --launch-gui %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
    echo.
    echo [setup] The application exited with code %CODE%.
    pause
)
exit /b %CODE%

:fail
echo.
echo [setup] Could not prepare a Python runtime.
echo [setup] Install Python 3.10+ from https://www.python.org/downloads/ and try again.
pause
exit /b 1
