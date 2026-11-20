@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Actualizando datos desde Gmail...
python -W ignore sincronizar.py
if errorlevel 1 (
  echo.
  echo Algo fallo. Si dice invalid_grant, borra token_organizar.json y ejecuta: python organizar_correos.py --simular
  pause
  exit /b 1
)
start "" dashboard.html
