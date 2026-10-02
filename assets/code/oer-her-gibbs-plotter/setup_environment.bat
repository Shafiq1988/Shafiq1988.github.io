@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.12 or newer, then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the private Python environment...
  py -3.12 -m venv .venv
)

echo Installing or updating the required plotting packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

if errorlevel 1 (
  echo.
  echo Setup did not finish successfully.
  pause
  exit /b 1
)

echo.
echo Setup complete.
pause
