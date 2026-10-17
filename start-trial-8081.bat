@echo off
chcp 65001 >nul
title 华立转角 · 试用版 8081
cd /d "%~dp0Backend mission"

echo.
echo   华立转角 · 学院试用版
echo   ----------------------------------------

rem 必须用装了 Pillow 的 Python：server.py 一启动就 import PIL。
rem 裸写 python 有风险 —— 机器上若装了多个 Python（某些工具会把自己的
rem 运行环境加进 PATH），靠前的那个未必有 Pillow，会直接报
rem ModuleNotFoundError: No module named 'PIL'，窗口一闪而过看不出原因。
rem 所以先试系统 3.8 的绝对路径，不存在再退回 PATH 里的 python。
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python38\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [错误] 找不到带 Pillow 的 Python，服务没有启动。
    echo   试过的解释器：%PY%
    echo   请安装 Pillow，或把本脚本里的 PY 改成正确的 python.exe 路径。
    echo.
    pause
    exit /b 1
)

echo   检查 8081 端口占用...
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8081" ^| findstr "LISTENING"') do (
    echo   发现已在运行的实例 PID %%p，先关闭它
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="1" timeout /t 2 /nobreak >nul

echo   启动中，请稍候...
echo   本机打开： http://127.0.0.1:8081
echo   别的电脑/手机：用下面打印的「局域网访问」地址（需同一 WiFi）
echo   停止服务：在此窗口按 Ctrl+C
echo   ----------------------------------------
echo.

rem --lan：开放局域网访问（自动绑定 0.0.0.0 并推导 Origin）。
rem 不加的话只监听本机，别人的电脑即使地址对也连不上。
"%PY%" server.py --trial --port 8081 --lan

echo.
echo   服务已停止。
pause
