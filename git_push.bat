@echo off
cd /d "%~dp0"
if exist ".git\index.lock" del /f ".git\index.lock"
git config user.name "nan29077"
git config user.email "uncleku77@gmail.com"
git add .
git commit -m "beautypos initial commit"
git remote remove origin 2>nul
git remote add origin https://github.com/nan29077/beautypos.git
git branch -M main
git push -u origin main
pause
