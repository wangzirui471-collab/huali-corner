@echo off
rem ---------------------------------------------------------------
rem  Huali Corner - MySQL-backed trial server launcher (port 8081)
rem
rem  This file is ASCII-only on purpose: cmd.exe parses .bat with the
rem  OEM codepage and splits multi-byte UTF-8, turning Chinese text
rem  into "not recognized as an internal or external command".
rem
rem  What it does:
rem    1. Starts mysqld (loopback only) if MySQL is not already up.
rem    2. Points the app at MySQL via HC_DB (SQLite stays as fallback
rem       when HC_DB is unset, e.g. via start-trial-8081.bat).
rem    3. Launches the trial server on port 8081 with --lan.
rem ---------------------------------------------------------------
title Huali Corner - MySQL Trial 8081
cd /d "%~dp0Backend mission"

echo.
echo   Huali Corner - MySQL Trial (port 8081)
echo   ---------------------------------------
echo.

rem Pillow + pymysql are required under MySQL mode.
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python38\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -c "import PIL, pymysql" >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] No Python with Pillow + pymysql found, server not started.
    echo   Tried interpreter: %PY%
    echo.
    pause
    exit /b 1
)

rem ---- Ensure MySQL is running (loopback only) ----
set "MYSQLD=C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqld.exe"
set "MYSQL_DATA=C:\ProgramData\MySQL\MySQL Server 8.4\Data"
set MYSQL_UP=0
for /f "tokens=2" %%p in ('netstat -ano ^| findstr ":3306" ^| findstr "LISTENING"') do set MYSQL_UP=1
if "%MYSQL_UP%"=="0" (
    if exist "%MYSQLD%" (
        echo   Starting mysqld (loopback only)...
        start "" "%MYSQLD%" --datadir="%MYSQL_DATA%" --bind-address=127.0.0.1 --console
    ) else (
        echo   [WARN] mysqld not found at %MYSQLD%; assuming MySQL is provided elsewhere.
    )
) else (
    echo   MySQL already running on 3306.
)

rem Wait for MySQL to accept connections (top-level loop, no label/goto in parens).
set /a WAIT=0
:wait_mysql
set MYSQL_UP=0
for /f "tokens=2" %%p in ('netstat -ano ^| findstr ":3306" ^| findstr "LISTENING"') do set MYSQL_UP=1
if NOT "%MYSQL_UP%"=="0" goto mysql_ready
if %WAIT% GEQ 30 goto mysql_ready
timeout /t 1 /nobreak >nul
set /a WAIT+=1
goto wait_mysql
:mysql_ready

rem ---- Point the app at MySQL ----
set "HC_DB=mysql://root@127.0.0.1:3306/huali_corner"

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

rem --trial matches the migrated var-trial data in MySQL.
rem --lan: listen on 0.0.0.0 so LAN/phone clients can reach it.
rem To switch back to SQLite, run start-trial-8081.bat instead.
"%PY%" server.py --trial --port 8081 --lan

echo.
echo   Server stopped.
pause
