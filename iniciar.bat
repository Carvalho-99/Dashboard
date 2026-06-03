@echo off
cd /d "%~dp0"

:: Primeira vez: configuracao necessaria (visivel, so acontece uma vez)
if not exist "venv\" (
    echo Configurando pela primeira vez, aguarde...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
)

:: Mata qualquer servidor anterior na porta 5050
powershell -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalPort 5050 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" 2>nul

:: Inicia servidor invisivel e abre o programa em janela separada do Edge
start "" powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%~dp0venv\Scripts\python.exe' -ArgumentList '%~dp0app.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden; Start-Sleep 3; try { Start-Process 'msedge' -ArgumentList '--app=http://localhost:5050 --new-window' } catch { Start-Process 'http://localhost:5050' }"
