@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_environment.bat
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" plot_figures.py --settings settings_user.json %*
if errorlevel 1 pause
