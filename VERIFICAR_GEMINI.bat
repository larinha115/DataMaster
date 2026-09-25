@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\verificar_gemini.py --test
) else (
  py -3 scripts\verificar_gemini.py --test
)
echo.
echo Se o modelo do .env nao aparecer na lista, altere GEMINI_MODEL no .env e reinicie o servidor.
pause
