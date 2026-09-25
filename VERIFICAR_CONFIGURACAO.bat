@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\diagnostico.py
) else (
  python scripts\diagnostico.py
)
echo.
pause
