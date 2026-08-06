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

REM --- Open preview in browser after 8s ---
start "" /b cmd /c "timeout /t 8 /nobreak >nul && start http://localhost:%SERVER_PORT%/"

REM --- Listen on every network interface so LAN devices can connect ---
%PYEXE% -m uvicorn app.main:app --reload --port %SERVER_PORT% --host 0.0.0.0
pause
