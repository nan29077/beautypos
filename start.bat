@echo off
cd /d "%~dp0"

REM --- Detect Python launcher from PATH ---
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE (
    where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
    echo [ERROR] Python not found. Install from https://www.python.org and add it to PATH.
    pause
    exit /b 1
)

echo [INFO] Using Python: %PYEXE%
%PYEXE% -m pip install -r requirements.txt

REM --- Open preview in browser after 8s ---
start "" /b cmd /c "timeout /t 8 /nobreak >nul && start http://localhost:3000/"

REM --- Run dev server on port 3000 ---
%PYEXE% -m uvicorn app.main:app --reload --port 3000 --host 0.0.0.0
pause
