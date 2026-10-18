@echo off
setlocal
set "PYTHONUTF8=1"
title Huali Corner - Trial 8081
cd /d "%~dp0"
if exist ".venv-trial\Scripts\python.exe" goto managed
where py.exe >nul 2>&1
if not errorlevel 1 goto launcher
where python.exe >nul 2>&1
if not errorlevel 1 goto python
where python3.exe >nul 2>&1
if not errorlevel 1 goto python3
echo [ERROR] Python was not found. Install 64-bit Python 3.12 or 3.13.
pause
exit /b 1
:managed
".venv-trial\Scripts\python.exe" "scripts\launch_trial.py" %*
set "LAUNCH_STATUS=%ERRORLEVEL%"
goto done
:launcher
py.exe -3 "scripts\launch_trial.py" %*
set "LAUNCH_STATUS=%ERRORLEVEL%"
goto done
:python
python.exe "scripts\launch_trial.py" %*
set "LAUNCH_STATUS=%ERRORLEVEL%"
goto done
:python3
python3.exe "scripts\launch_trial.py" %*
set "LAUNCH_STATUS=%ERRORLEVEL%"
:done
if not "%LAUNCH_STATUS%"=="0" pause
exit /b %LAUNCH_STATUS%
