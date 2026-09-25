@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\usar_planilha.py
) else (
  py -3 scripts\usar_planilha.py 2>nul
  if errorlevel 1 python scripts\usar_planilha.py
)
if errorlevel 1 echo Nao foi possivel ativar a planilha. Confira as instrucoes acima.
pause
