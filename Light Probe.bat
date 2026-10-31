@echo off
setlocal EnableExtensions
title Light Probe
rem ============================================================================
rem  Light Probe - double-click to start.
rem  First run: sets up Python packages in .venv (a few minutes, needs internet once).
rem  Later runs: starts straight away. If Light Probe is already open, it is
rem  closed and started again.
rem ============================================================================
cd /d "%~dp0"

rem ---- 1. Python 3.12-3.14 ----------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 12), (3, 13), (3, 14)) else 1)" >nul 2>&1
    if not errorlevel 1 goto :packages
    echo The existing Python environment is stale or broken. Recreating it...
    rmdir /s /q ".venv"
)
call :find_python
if not defined PY (
    echo Light Probe currently needs Python 3.12, 3.13, or 3.14.
    echo Python 3.15 is installed, but one of Light Probe's packages has no
    echo compatible Python 3.15 wheel yet and would require C++ build tools.
    where winget >nul 2>&1 && (
        choice /M "Install Python 3.13 now"
        if errorlevel 2 goto :no_python
        winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
        call :find_python
    )
)
if not defined PY goto :no_python
echo Setting up a fresh environment with %PY%...
%PY% -m venv .venv || goto :failed

rem ---- 2. Packages (first run, or when requirements.txt changed) ----------------
:packages
fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1 && goto :start
echo Installing Light Probe's packages (one time)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :failed
copy /y requirements.txt ".venv\requirements.installed" >nul

rem ---- 3. Start (closes a copy that is already open) -----------------------------
:start
rem A copy that is already open is closed first, so this always starts a fresh one
".venv\Scripts\python.exe" run.py --stop
echo Starting Light Probe...
start "" ".venv\Scripts\pythonw.exe" run.py %*
rem Give it a moment, then make sure it actually came up
for /l %%i in (1,1,30) do (
    ping -n 2 127.0.0.1 >nul
    curl -s -o nul http://127.0.0.1:8765/ && goto :started
)
echo.
echo Light Probe did not start. The last lines of lightprobe.log:
if exist lightprobe.log powershell -NoProfile -Command "Get-Content lightprobe.log -Tail 25"
pause
exit /b 1

:started
exit /b 0

:find_python
set "PY="
for %%V in (3.14 3.13 3.12) do if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
)
exit /b 0

:no_python
echo Please install Python 3.13 from https://www.python.org/downloads/
echo (tick "Add python.exe to PATH"), then double-click Light Probe.bat again.
pause
exit /b 1

:failed
echo.
echo Setup failed - see the messages above. Check the internet connection and try again.
pause
exit /b 1
