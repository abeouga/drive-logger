@echo off
rem ct125-app: start the Vite dev server and open http://localhost:5173 (Ctrl+C to stop)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1" %*
if errorlevel 1 pause
