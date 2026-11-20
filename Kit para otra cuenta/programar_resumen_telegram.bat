@echo off
chcp 65001 >nul
rem Programa el resumen de Gmail por Telegram. Edita las horas y ejecuta una vez.
rem Quitar: schtasks /Delete /TN "Resumen Gmail Telegram 1900" /F  (y lo mismo con 2100)
cd /d "%~dp0"
set "BAT=%~dp0ejecutar_resumen.bat"
schtasks /Create /F /SC DAILY /ST 19:00 /TN "Resumen Gmail Telegram 1900" /TR "\"%BAT%\""
schtasks /Create /F /SC DAILY /ST 21:00 /TN "Resumen Gmail Telegram 2100" /TR "\"%BAT%\""
echo.
echo Listo: resumen diario a las 19:00 y a las 21:00. El computador debe estar encendido.
pause
