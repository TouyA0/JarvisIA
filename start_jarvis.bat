@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "start_jarvis.ps1"
echo.
echo Jarvis s'est arrete. Appuie sur une touche pour fermer.
pause >nul
