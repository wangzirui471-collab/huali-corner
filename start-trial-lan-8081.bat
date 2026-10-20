@echo off
chcp 65001 >nul
title 华立转角 · 试用版 8081（局域网+3080）
cd /d "%~dp0Backend mission"

rem 必须用装了 Pillow 的 Python：server.py 一启动就 import PIL。
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python38\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [错误] 找不到带 Pillow 的 Python，服务没有启动。
    echo   试过的解释器：%PY%
    pause
    exit /b 1
)

rem 清理 8081 / 3080 上可能残留的旧实例，避免多进程抢端口。
rem 这是「一改就打不开」最常见的根因：旧进程没死、新进程起不来。
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8081" ^| findstr "LISTENING"') do (
    echo   清理 8081 旧实例 PID %%p
    taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3080" ^| findstr "LISTENING"') do (
    echo   清理 3080 旧实例 PID %%p
    taskkill /PID %%p /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo   启动中，请稍候...
echo   本机访问： http://127.0.0.1:8081  或  http://127.0.0.1:3080
echo   停止服务：在此窗口按 Ctrl+C
echo.
"%PY%" server.py --trial --port 8081 --lan --extra-port 3080
echo.
echo   服务已停止。
pause
