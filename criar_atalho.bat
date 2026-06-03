@echo off
title Criando atalho - Organizador Financeiro
cd /d "%~dp0"

:: Ativa venv se existir
if exist "venv\Scripts\activate.bat" call venv\Scripts\activate.bat

:: Instala Pillow se precisar
python -c "import PIL" >nul 2>&1
if errorlevel 1 pip install pillow --quiet

:: Gera o icone
python gerar_icone.py

:: Cria atalho na Area de Trabalho
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Organizador Financeiro.lnk'); $s.TargetPath = '%~dp0iniciar.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0icone.ico'; $s.Description = 'Organizador Financeiro'; $s.Save()"

echo.
echo ========================================
echo  Atalho criado na Area de Trabalho!
echo  Icone: circulo verde com simbolo $
echo ========================================
echo.
pause
