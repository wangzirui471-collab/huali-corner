@echo off
chcp 65001 >nul
title 转角 · AI 客服（本机开源模型）
cd /d "%~dp0"

echo.
echo   转角 · AI 客服 本机开源模型版
echo   数据不出本机：知识库检索 + DeepSeek-R1-Distill-Qwen 在本机生成
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-ai-local.ps1" %*

echo.
echo   AI 服务已退出。
pause
