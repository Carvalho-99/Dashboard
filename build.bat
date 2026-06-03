@echo off
title Compilando Organizador Financeiro
cd /d "%~dp0"

echo ========================================
echo  GERANDO EXECUTAVEL
echo ========================================
echo.

:: Ativa o ambiente virtual se existir
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: Instala dependencias
pip install pyinstaller pillow --quiet

echo Compilando servidor... (1 a 2 minutos)
echo.

pyinstaller ^
    --name "OrganizadorFinanceiro" ^
    --onedir ^
    --add-data "%~dp0templates;templates" ^
    --add-data "%~dp0static;static" ^
    --distpath "comprador" ^
    --workpath "build_temp" ^
    --specpath "build_temp" ^
    --noconfirm ^
    app.py

echo.
echo Gerando icone...
python gerar_icone.py

echo Compilando launcher...
echo.

pyinstaller ^
    --name "Organizador Financeiro" ^
    --onefile ^
    --noconsole ^
    --icon "%~dp0icone.ico" ^
    --distpath "comprador\OrganizadorFinanceiro" ^
    --workpath "build_temp" ^
    --specpath "build_temp" ^
    --noconfirm ^
    launcher.py

:: Limpa arquivos temporarios
if exist "build_temp" rmdir /s /q "build_temp"
if exist "icone.ico" del "icone.ico"

:: Copia LEIA-ME
copy /Y "comprador_leiame.txt" "comprador\OrganizadorFinanceiro\LEIA-ME.txt" >nul 2>&1

:: Remove Iniciar.bat antigo (substituido pelo exe com icone)
if exist "comprador\OrganizadorFinanceiro\Iniciar.bat" del "comprador\OrganizadorFinanceiro\Iniciar.bat"

echo.
echo ========================================
echo  PRONTO!
echo ========================================
echo  Pasta pronta: comprador\OrganizadorFinanceiro\
echo  Compacte ela e envie ao comprador.
echo ========================================
echo.
pause
