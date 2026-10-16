@echo off
chcp 65001 >nul
title 转角 · 模拟试用版 8081
cd /d "%~dp0"
echo.
echo 转角 · 手机号密码登录 · 全部交易为模拟
python -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo 请先安装 Python 3.12，再运行下面的依赖安装命令：
    echo python -m pip install -r "Backend mission/requirements.txt"
    pause
    exit /b 1
)
echo 启动后在浏览器打开 http://127.0.0.1:8081
echo 请保持此窗口运行。停止时按 Ctrl+C。
echo 端口被占用时请使用另一个启动脚本，或自行结束旧实例。
python "Backend mission/server.py" --trial --port 8081
echo 服务已停止；如有报错，请保留上面的完整信息。
pause
