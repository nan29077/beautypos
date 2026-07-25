@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "LOG=%~dp0_server_log.txt"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "DATABASE_URL_OVERRIDE=sqlite:///./adpay.db"
echo === SERVER START %DATE% %TIME% === > "%LOG%"
REM --- Open the site root (not /docs) in browser after 6s ---
start "" /b cmd /c "timeout /t 6 /nobreak >nul && start http://localhost:3000/"
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 3000 >> "%LOG%" 2>&1
echo === SERVER EXITED %errorlevel% %DATE% %TIME% === >> "%LOG%"
pause
