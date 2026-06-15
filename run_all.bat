@echo off
chcp 65001 >nul
:: run_all.bat - 双击就能跑餐补工具链
:: 自动以 Bypass 策略调 PowerShell,无需改全局设置

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_all.ps1"
pause
