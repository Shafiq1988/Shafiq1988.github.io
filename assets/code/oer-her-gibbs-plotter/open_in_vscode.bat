@echo off
setlocal
cd /d "%~dp0"
where code >nul 2>nul
if not errorlevel 1 (
  code OER_HER_Figure_Editor.code-workspace
  exit /b 0
)
if exist "%LocalAppData%\Programs\Microsoft VS Code\Code.exe" (
  start "" "%LocalAppData%\Programs\Microsoft VS Code\Code.exe" OER_HER_Figure_Editor.code-workspace
  exit /b 0
)
echo VS Code was not found. Run setup or open this folder in your preferred editor.
pause
