@echo off
cd /d "%~dp0"
if exist ".venv-gui\Scripts\python.exe" goto launch
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import tkinter; tkinter.Tk().destroy()" >nul 2>&1
    if not errorlevel 1 goto launch_default
)
echo 未找到可用的 Tk 图形环境。
echo 请使用带 Tk 的 Python 3.10+ 执行:
echo   python -m venv .venv-gui
echo   .venv-gui\Scripts\python.exe -m pip install -r requirements.txt
pause
exit /b 1

:launch
".venv-gui\Scripts\python.exe" main.py --gui
set "gui_code=%errorlevel%"
if not "%gui_code%"=="0" pause
exit /b %gui_code%

:launch_default
".venv\Scripts\python.exe" main.py --gui
set "gui_code=%errorlevel%"
if not "%gui_code%"=="0" pause
exit /b %gui_code%
