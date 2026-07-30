@echo off
cd /d E:\프로젝트\beautypos
if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock
git remote set-url origin https://github.com/nan29077/beautypos.git
git push origin main
git log --oneline -3
pause
