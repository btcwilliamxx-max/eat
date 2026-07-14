@echo off
chcp 65001 >nul
:: 长期解决方案: 起 serve_watchdog.py
:: 它会起 serve.py 在 8765 端口, 每 30 秒健康检查, 卡了自动重启
:: 双击这个, 黑窗口最小化, 长期挂着
:: 关闭: 关掉黑窗口 / Ctrl+C

cd /d "%~dp0"
python -X utf8 "%~dp0serve_watchdog.py"
pause