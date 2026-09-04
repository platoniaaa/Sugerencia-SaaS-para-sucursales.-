@echo off
REM Doble clic aqui para dejar este computador atendiendo el boton "Actualizar ahora"
REM de la plataforma. Se hace una sola vez. Los .ps1 no se pueden ejecutar con doble
REM clic (Windows los abre en el Bloc de notas), por eso existe este atajo.
title Sugerido de Compras - instalar el agente
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar_agente.ps1"
