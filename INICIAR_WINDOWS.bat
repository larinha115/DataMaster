@echo off
setlocal
cd /d "%~dp0"
title DATA MASTER - Cyber Risk Assessment
if not exist ".venv\Scripts\python.exe" (
  echo Preparando ambiente Python. Isso so e necessario na primeira execucao...
  py -3.12 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" python -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" (
    echo ERRO: Python 3.11 ou 3.12 nao encontrado. Instale Python e tente novamente.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Falha na instalacao das dependencias. Confira sua conexao e mensagens acima.
    pause
    exit /b 1
  )
)
REM Atualiza automaticamente o SDK antigo 1.x usado pelas versoes anteriores.
".venv\Scripts\python.exe" -c "import importlib.metadata as m,sys; sys.exit(0 if 2 <= int(m.version('google-genai').split('.')[0]) < 3 else 1)" >nul 2>&1
if errorlevel 1 (
  echo Atualizando google-genai para a versao compativel com este projeto...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Falha ao atualizar as dependencias. Confira sua conexao e mensagens acima.
    pause
    exit /b 1
  )
)
if not exist ".env" copy ".env.example" ".env" >nul
if exist "SBK_Framework_NIST.xlsx" (
  ".venv\Scripts\python.exe" scripts\usar_planilha.py
  if errorlevel 1 (pause & exit /b 1)
) else if exist "data\privado\SBK_Framework_NIST.xlsx" (
  ".venv\Scripts\python.exe" scripts\usar_planilha.py
  if errorlevel 1 (pause & exit /b 1)
)
echo.
echo Abra http://127.0.0.1:8000 no navegador para carregar os controles.
echo Se a tela foi aberta antes do servidor, clique em Tentar conectar novamente.
echo O modo DEMONSTRACAO funciona sem GOOGLE_API_KEY. Para analise real, configure a chave no .env.
echo.
start "" powershell -NoProfile -Command "Start-Sleep -Seconds 5; Start-Process 'http://127.0.0.1:8000/'"
".venv\Scripts\python.exe" -m uvicorn api3:app --host 127.0.0.1 --port 8000
pause
