@echo off
cd /d "%~dp0Backend mission"
python server.py --trial --port 8080
pause
