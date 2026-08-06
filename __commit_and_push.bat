@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] git lock 파일 제거 중...
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock" del /f ".git\HEAD.lock"

echo [2/3] 변경사항 커밋 중...
git add -A
git commit -m "광고 집행 현황 카드+바텀시트/팝업 UI 개선 및 KST·회원가입 전면 개편"

echo [3/3] 푸시 중...
git push

echo.
echo 완료! 서버를 재시작해 주세요.
pause
