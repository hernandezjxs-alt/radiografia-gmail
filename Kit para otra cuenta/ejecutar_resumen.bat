@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -W ignore resumen_telegram.py --sincronizar --dias 1 >> resumen_telegram.log 2>&1
