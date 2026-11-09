@echo off
rem drive-logger: start the web app dev server and open http://localhost:5173 (Ctrl+C to stop)
rem The steps are in web\scripts\start-dev.ps1. Option: -NoBrowser
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
