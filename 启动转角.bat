@echo off
setlocal
cd /d "%~dp0"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8081"
set "DATA=%~2"
set "ARGS=--port %PORT%"
rem 默认同时监听 3080，方便沿用旧习惯的 3080 地址；同一进程、同一份数据。
if not "%PORT%"=="3080" set ARGS=%ARGS% --extra-port 3080
if not "%DATA%"=="" set ARGS=%ARGS% --data "%DATA%"
set "OPEN_PORT=%ZJ_OPEN_PORT%"
if "%OPEN_PORT%"=="" set "OPEN_PORT=%PORT%"
title 华立转角 · 临时服务 %PORT%（另含 %OPEN_PORT%）

curl -s -m 2 "http://127.0.0.1:%OPEN_PORT%/api/health" >nul 2>&1
if not errorlevel 1 goto open

echo 本地服务未启动，正在拉起（约几秒）...
start "" /min "%~dp0start-trial-8081.bat" %ARGS%

for /l %%i in (1,1,40) do (
  curl -s -m 2 "http://127.0.0.1:%OPEN_PORT%/api/health" >nul 2>&1
  if not errorlevel 1 goto open
  ping -n 2 127.0.0.1 >nul
)

echo.
echo [启动失败] 40 次轮询仍未连上
echo 请查看最小化那个窗口，把第一条 ERROR 信息发我
echo 常见原因：端口被占、Python 被卸载、项目目录被移动
if "%ZJ_NO_OPEN%"=="1" exit /b 1
pause
exit /b 1

:open
if "%ZJ_NO_OPEN%"=="1" (
  echo 本地服务已就绪：http://127.0.0.1:%OPEN_PORT%/  (ZJ_NO_OPEN=1 已跳过打开浏览器)
  exit /b 0
)
start "" "http://127.0.0.1:%OPEN_PORT%/#home"
exit /b 0
