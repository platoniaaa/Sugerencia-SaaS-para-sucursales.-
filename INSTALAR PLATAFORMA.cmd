@echo off
REM ============================================================
REM  INSTALAR PLATAFORMA.cmd - Deja este PC manteniendo la plataforma al dia
REM
REM  Doble clic y seguir lo que dice la ventana. Se puede repetir sin problema.
REM  Sirve de dos formas:
REM   - dentro de la carpeta del motor (al lado de "scripts"): usa ese instalador;
REM   - como archivo suelto (por correo, en el Escritorio): baja de GitHub la ultima
REM     version del instalador y la corre. Si no hay internet pero el motor ya esta
REM     instalado en este PC, usa el instalador que trae.
REM  Los .ps1 no se pueden abrir con doble clic (Windows los abre en el Bloc de
REM  notas): por eso existe este archivo.
REM ============================================================
setlocal
title Instalar plataforma de sugerido
set "INSTALADOR=%~dp0scripts\instalar_pc_jefa.ps1"
if exist "%INSTALADOR%" goto correr

set "INSTALADOR=%TEMP%\instalar_pc_jefa.ps1"
set "URL=https://raw.githubusercontent.com/platoniaaa/Sugerencia-SaaS-para-sucursales.-/arreglar-job-diario/scripts/instalar_pc_jefa.ps1"
if exist "%INSTALADOR%" del /q "%INSTALADOR%"
echo Bajando el instalador desde GitHub...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = 'Tls12'; Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%INSTALADOR%' } catch { Write-Host ('  (' + $_.Exception.Message + ')') }"
if exist "%INSTALADOR%" goto correr

set "INSTALADOR=%USERPROFILE%\dev\Sugerencia-SaaS-para-sucursales\scripts\instalar_pc_jefa.ps1"
if exist "%INSTALADOR%" (
    echo No se pudo bajar: se usa el instalador del motor que ya esta en este PC.
    goto correr
)
echo.
echo No se pudo bajar el instalador. Revisa que el PC tenga internet y vuelve a
echo hacer doble clic en este archivo.
pause
exit /b 1

:correr
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALADOR%"
if errorlevel 1 (
    echo.
    echo El instalador no termino bien. Lee los mensajes de arriba: dicen que falta.
    echo Si la ventana se cerro sin mostrar nada, puede que Windows no deje correr
    echo scripts de PowerShell en este PC: en ese caso hay que pedirselo a TI.
    pause
)
endlocal
