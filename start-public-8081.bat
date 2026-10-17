@echo off
chcp 65001 >nul
title 华立转角 · 公网访问（Cloudflare Tunnel）

set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python38\python.exe"
if not exist "%PY%" set "PY=python"

rem --- 找 cloudflared ---
set "CF="
where cloudflared >nul 2>&1 && set "CF=cloudflared"
if not defined CF if exist "%ProgramFiles%\cloudflared\cloudflared.exe" set "CF=%ProgramFiles%\cloudflared\cloudflared.exe"
if not defined CF if exist "%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe" set "CF=%LocalAppData%\Microsoft\WinGet\Links\cloudflared.exe"

if not defined CF (
    echo.
    echo   [缺少工具] 没有找到 cloudflared。
    echo.
    echo   任选一种安装：
    echo     1^) winget install --id Cloudflare.cloudflared
    echo     2^) 下载 https://github.com/cloudflare/cloudflared/releases/latest
    echo        里的 cloudflared-windows-amd64.exe，改名 cloudflared.exe 放进 PATH
    echo.
    echo   装好后重新双击本脚本。
    pause
    exit /b 1
)

echo.
echo   华立转角 · 公网访问
echo   ----------------------------------------
echo   后端只监听本机 127.0.0.1:8081，由隧道对外转发。
echo   启动后下面会打印一个 https://xxxx.trycloudflare.com 地址，
echo   发给别人即可全国访问；关掉本窗口地址立即失效。
echo   ----------------------------------------
echo.

cd /d "%~dp0Backend mission"
start "huali-8081-backend" "%PY%" server.py --trial --port 8081

echo   等待后端启动...
timeout /t 3 /nobreak >nul

echo   正在建立公网隧道，请稍候...
echo.
"%CF%" tunnel --url http://127.0.0.1:8081

echo.
echo   隧道已结束。若后端窗口仍在，可按需关闭。
pause
