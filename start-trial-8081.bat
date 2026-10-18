@echo off
setlocal
set "PYTHONUTF8=1"
set "ZJ_BOOTSTRAP_CMD="
title Huali Corner - Trial 8081
cd /d "%~dp0"
if not exist "scripts\launch_trial.py" goto missing_helper
echo Checking installed Python interpreters...
call :probe "%~dp0.venv-trial\Scripts\python.exe"
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe "%ProgramFiles%\Python312\python.exe"
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe "%ProgramFiles%\Python313\python.exe"
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe python.exe
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe python3.exe
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe py.exe -3.12
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe py.exe -3.13
if defined ZJ_BOOTSTRAP_CMD goto run
call :probe py.exe -3
if defined ZJ_BOOTSTRAP_CMD goto run
echo [ERROR] No working Python 3.8 or newer was found.
echo The Python launcher may point to an interpreter that no longer starts.
echo Keep your project data. Install or repair 64-bit Python 3.12 or 3.13.
pause
exit /b 1
:missing_helper
echo [ERROR] Missing scripts\launch_trial.py. Copy the repair files into the project root.
pause
exit /b 1
:run
%ZJ_BOOTSTRAP_CMD% "scripts\launch_trial.py" %*
set "LAUNCH_STATUS=%ERRORLEVEL%"
if not "%LAUNCH_STATUS%"=="0" pause
exit /b %LAUNCH_STATUS%
:probe
rem A registered launcher or existing file is not proof that Python can start.
%* -c "import sys; assert sys.version_info >= (3, 8)" >nul 2>&1
if errorlevel 1 exit /b 1
set "ZJ_BOOTSTRAP_CMD=%*"
exit /b 0
