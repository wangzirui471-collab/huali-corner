@echo off
chcp 65001 >nul
title 华立转角 · 试用版 8080
cd /d "%~dp0Backend mission"

echo.
echo   华立转角 · 学院试用版
echo   ----------------------------------------
echo   检查 8080 端口占用...
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8080" ^| findstr "LISTENING"') do (
    echo   发现已在运行的实例 PID %%p，先关闭它
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="1" timeout /t 2 /nobreak >nul

echo   启动中，请稍候...
echo   浏览器打开： http://127.0.0.1:8080
echo   停止服务：在此窗口按 Ctrl+C
echo   ----------------------------------------
echo.

python server.py --trial --port 8080

echo.
echo   服务已停止。
pause
