@echo off
rem ---------------------------------------------------------------
rem  Huali Corner - trial server launcher (port 8081)
rem
rem  Why is this file ASCII-only? cmd.exe parses .bat files with the
rem  OEM codepage and splits multi-byte UTF-8 characters, which makes
rem  it run half-characters as commands:
rem      '了多个' is not recognized as an internal or external command
rem  Keeping the batch file pure ASCII removes that class of noise.
rem  Chinese user-facing text is printed by server.py itself.
rem ---------------------------------------------------------------
title Huali Corner - Trial 8081
cd /d "%~dp0Backend mission"

echo.
echo   Huali Corner - Campus Trial (port 8081)
echo   ----------------------------------------
echo.

rem Pillow is required: server.py imports PIL at startup.
rem A bare "python" cannot be trusted (this machine has several
rem interpreters on PATH and the first one may lack Pillow), so
rem try the known 3.8 install first and fall back to PATH python.
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python38\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] No Python with Pillow found, server not started.
    echo   Tried interpreter: %PY%
    echo   Install Pillow, or fix the PY path inside this script.
    echo.
    pause
    exit /b 1
)

echo   Checking port 8081...
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8081" ^| findstr "LISTENING"') do (
    echo   Found running instance PID %%p, closing it
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="1" timeout /t 2 /nobreak >nul

echo   Starting, please wait...
echo   Local:  http://127.0.0.1:8081
echo   Phones/other PCs: use the LAN address printed below (same WiFi)
echo   Stop:   press Ctrl+C in this window
echo   ----------------------------------------
echo.

rem --lan: listen on 0.0.0.0 and derive the LAN origin automatically.
rem Without it the server only listens on localhost and phones on the
rem same WiFi cannot connect.
"%PY%" server.py --trial --port 8081 --lan

echo.
echo   Server stopped.
pause
