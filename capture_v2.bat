@echo off
cd /d "%~dp0"
python -X utf8 "%~dp0capture_v2.py" %*
echo.
pause
