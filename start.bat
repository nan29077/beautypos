@echo off
cd /d "%~dp0"
set "SERVER_PORT=3000"
set "LOCAL_IP="

REM --- Detect the current LAN IPv4 address without administrator rights ---
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ips=[System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()); ($ips.Where({$_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and $_.IPAddressToString -notlike '169.254*'})[0]).IPAddressToString"`) do set "LOCAL_IP=%%I"

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

echo.
echo   BEAUTYPOS development server
echo   - Local:   http://localhost:%SERVER_PORT%/
if defined LOCAL_IP (
    echo   - Network: http://%LOCAL_IP%:%SERVER_PORT%/
) else (
    echo   - Network: IP address could not be detected.
)
echo   - Same Wi-Fi/LAN devices can open the Network address.
echo.

REM --- Apply pending database migrations --------------------------------
REM  create_all is only able to create NEW tables. Columns added to an
REM  existing table never appear, and the server answers 500 with
REM  "Unknown column". deploy.sh does this on the server; do it here too.
REM  Kept non-fatal: a migration problem should not block local work.
echo [INFO] Applying database migrations...
%PYEXE% -m alembic upgrade head
if errorlevel 1 (
    echo.
    echo [WARN] Migration failed. Pages that use new columns may return 500.
    echo        Check the current revision with:
    echo            %PYEXE% -m alembic current
    echo.
)

REM --- Refuse to start when the port is already taken ---------------------
REM  A leftover server keeps serving OLD code: new menus show up (static files
REM  are read from disk) but new API routes answer 404. Starting a second
REM  instance just fails to bind and hides the real problem.
REM  The check connects to the port with Python so it does not depend on the
REM  wording of netstat output.
%PYEXE% -c "import socket,sys; s=socket.socket(); s.settimeout(1); r=s.connect_ex(('127.0.0.1',%SERVER_PORT%)); s.close(); sys.exit(1 if r==0 else 0)"
if errorlevel 1 (
    echo.
    echo [ERROR] Port %SERVER_PORT% is already in use - an older server is still running.
    echo         It keeps serving OLD code, so new API routes will return 404.
    echo         Find the process id in the last column below and close it:
    echo.
    netstat -ano ^| findstr ":%SERVER_PORT%"
    echo.
    echo             taskkill /PID ^<process id^> /F
    echo.
    echo         Then run this file again.
    pause
    exit /b 1
)

REM --- Open preview in browser after 8s ---
start "" /b cmd /c "timeout /t 8 /nobreak >nul && start http://localhost:%SERVER_PORT%/"

REM --- Listen on every network interface so LAN devices can connect ---
%PYEXE% -m uvicorn app.main:app --reload --port %SERVER_PORT% --host 0.0.0.0
pause
