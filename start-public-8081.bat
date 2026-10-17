@echo off
rem ---------------------------------------------------------------
rem  Huali Corner - public tunnel (Cloudflare Quick Tunnel -> 8081)
rem
rem  ASCII-only on purpose: cmd.exe splits multi-byte UTF-8 in .bat
rem  files and runs the halves as commands.
rem
rem  --protocol http2 matters on this network: the default QUIC
rem  (UDP) path times out, http2 goes through fine.
rem ---------------------------------------------------------------
title Huali Corner - Public Tunnel 8081
cd /d "%~dp0"

set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python38\python.exe"
if not exist "%PY%" set "PY=python"

rem --- reuse a backend that is already listening, else start one ---
set "RUNNING="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8081" ^| findstr "LISTENING"') do set "RUNNING=1"
if defined RUNNING (
    echo   Backend already listening on 8081, reusing it.
) else (
    echo   Starting backend on 8081 in a new window...
    cd /d "%~dp0Backend mission"
    start "huali-backend-8081" "%PY%" server.py --trial --port 8081
    cd /d "%~dp0"
    timeout /t 4 /nobreak >nul
)

rem --- locate cloudflared ---
set "CF="
where cloudflared >nul 2>&1 && set "CF=cloudflared"
if not defined CF if exist "%~dp0tools\cloudflared.exe" set "CF=%~dp0tools\cloudflared.exe"
if not defined CF if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
if not defined CF if exist "%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe" set "CF=%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe"

if not defined CF (
    echo.
    echo   [MISSING] cloudflared not found.
    echo   Download cloudflared-windows-amd64.exe from
    echo     https://github.com/cloudflare/cloudflared/releases/latest
    echo   rename it cloudflared.exe and put it in:  %~dp0tools\
    echo.
    pause
    exit /b 1
)

echo.
echo   Huali Corner - public access
echo   ----------------------------------------
echo   Backend stays on this machine; the tunnel only forwards.
echo   A line like the one below will appear in a few seconds:
echo     https://xxxx-xxxx.trycloudflare.com
echo   That is the address to send to others. Closing this window
echo   kills it, and every restart gives a NEW address.
echo   ----------------------------------------
echo.

"%CF%" tunnel --url http://127.0.0.1:8081 --no-autoupdate --protocol http2

echo.
echo   Tunnel stopped.
pause
