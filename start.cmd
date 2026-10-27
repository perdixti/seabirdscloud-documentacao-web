@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
where python >nul 2>nul
if errorlevel 1 (
    echo Instale Python 3.12 ou 3.13 e marque "Add Python to PATH".
    pause
    exit /b 1
)
python -m venv .venv
if errorlevel 1 goto error
:run
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto error
echo Abra http://127.0.0.1:8000 no navegador. Ctrl+C encerra o servidor.
.venv\Scripts\python.exe main.py
if errorlevel 1 goto error
exit /b 0
:error
echo Nao foi possivel iniciar. Confira a mensagem acima.
pause
exit /b 1
