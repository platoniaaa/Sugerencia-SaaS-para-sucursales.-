@echo off
REM Doble clic aqui para traer los reemplazos y precios de FORD y publicarlos.
REM
REM Es lo mismo que hace la tarea automatica de los lunes a las 9:00. Sirve para
REM no esperar al lunes: tipicamente despues de renovar la sesion del portal.
REM
REM Los .ps1 no se pueden ejecutar con doble clic (Windows los abre en el Bloc de
REM notas), por eso existe este atajo.
title Sugerido de Compras - actualizar FORD
echo.
echo  ============================================================
echo   ACTUALIZAR REEMPLAZOS Y PRECIOS DE FORD
echo  ============================================================
echo.
echo   Consulta el portal de FORD y publica el resultado en la
echo   plataforma. Demora unos 30 minutos.
echo.
echo   Si la sesion del portal vencio, se va a abrir una ventana
echo   de Chrome pidiendo usuario, clave y MFA. Hay que entrar ahi
echo   para que la corrida siga. La sesion queda guardada.
echo.
echo   No cierres esta ventana hasta que diga LISTO.
echo.
pause

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\tarea_vigentes_ford.ps1"
set CODIGO=%ERRORLEVEL%

echo.
if "%CODIGO%"=="0" (
  echo  ============================================================
  echo   LISTO. La plataforma ya tiene los reemplazos y precios nuevos.
  echo  ============================================================
) else (
  echo  ============================================================
  echo   NO SE PUDO COMPLETAR ^(codigo %CODIGO%^)
  echo  ============================================================
  echo.
  echo   La causa mas comun es que la sesion del portal vencio.
  echo   Abri "Abrir App.bat" en la carpeta de extraccion de FORD,
  echo   inicia sesion una vez, y volve a correr este acceso.
  echo.
  echo   El detalle esta en la carpeta logs, en el archivo
  echo   vigentes_ford de hoy.
)
echo.
pause
