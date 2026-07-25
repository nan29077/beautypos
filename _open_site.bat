@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "LOG=%~dp0_verify_log.txt"
echo === SITE VERIFY %DATE% %TIME% === > "%LOG%"
curl -s -L -o nul -w "ROOT_FINAL=%%{http_code} URL=%%{url_effective}\n" http://localhost:3000/ >> "%LOG%" 2>&1
echo --- root page title --- >> "%LOG%"
curl -s -L http://localhost:3000/ | findstr /I "<title>" >> "%LOG%" 2>&1
echo === DONE %DATE% %TIME% === >> "%LOG%"
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --new-window "http://localhost:3000/"
exit
