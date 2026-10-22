' ============================================================
'  sin_ventana.vbs - Corre un script de PowerShell sin abrir ninguna ventana
'
'  Lo usan las tareas de Windows que deja instalar_pc_jefa.ps1:
'    wscript.exe //B //Nologo sin_ventana.vbs "<ruta>\script.ps1"
'
'  Con powershell.exe -WindowStyle Hidden directo, Windows igual muestra la ventana
'  un instante (y con Windows Terminal como consola por defecto la deja abierta).
'  La tarea del agente corre cada minuto: esa ventana le quitaria el foco al
'  programa del ERP mientras hace clics en Flexline. Asi no aparece nada.
'
'  Espera a que el script termine y devuelve su codigo de salida, para que el
'  Programador de tareas muestre si salio bien.
' ============================================================
If WScript.Arguments.Count < 1 Then WScript.Quit 2
Set shell = CreateObject("WScript.Shell")
comando = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & _
          WScript.Arguments(0) & """"
WScript.Quit shell.Run(comando, 0, True)
