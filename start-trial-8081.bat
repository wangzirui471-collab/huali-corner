@echo off
cd /d "%~dp0Backend mission"
python server.py --trial --port 8081
pause
