@echo off
chcp 65001 >nul
:: 启动本地 http server, 解决 index.html 用 file:// 打开时无法复制图片的问题
:: 浏览器自动打开 http://localhost:8765/index.html
:: 关闭: 关掉这个黑窗口 / Ctrl+C

cd /d "%~dp0"
python -X utf8 "%~dp0serve.py" %*
