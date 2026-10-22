@echo off
cd /d "%~dp0"
powershell -WindowStyle Hidden -Command "Start-Process -FilePath '%~dp0OrganizadorFinanceiro.exe' -WindowStyle Hidden; Start-Sleep -Seconds 2; Start-Process 'http://localhost:5050'"
