# Instalar la plataforma en tu PC

Tu PC va a calcular el sugerido de compras y publicarlo en la plataforma **cuando tú (o
alguien con permiso) aprietes "Actualizar ahora"**. Nada se calcula solo. Se instala una
vez, con doble clic, y tarda unos 10 minutos.

Las tablas del ERP las sigue bajando tu programa del ERP, el de siempre: deja los
archivos en `Bases de datos` y el motor los lee de ahí. Este instalador no lo toca.

## Antes de empezar

- Tu programa que baja las tablas del ERP, funcionando y dejando los archivos en
  `Documentos\Desarrollos\Bases de datos` de tu OneDrive.
- OneDrive de la empresa abierto, con tu cuenta (`OneDrive - Curifor S.A`).
- Internet.
- Dos claves que te pasa quien mantiene la plataforma: la de la **cuenta del motor**
  (`admin@curifor.com`) y la **clave del agente**. Se escriben sin que se vean y quedan
  guardadas solo en tu PC.

## Instalar

1. Haz doble clic en **`INSTALAR PLATAFORMA.cmd`** (te lo mandan como archivo suelto;
   déjalo en el Escritorio). Si Windows dice "Windows protegió su PC", elige
   **Más información** y **Ejecutar de todas formas**.
2. Sigue la ventana. Cuando una pregunta trae un valor entre `[corchetes]`, Enter lo
   acepta.
3. Al final lee el **Resumen**: dice qué quedó listo y, en "Falta", qué hacer con cada
   cosa. Se puede volver a correr cuantas veces haga falta: no pisa lo que está bien.

Si Windows pide permiso para instalar Python o Git, acéptalo. Si tu PC no te deja
instalar programas, el instalador usa el Python que trae el kit del programa del ERP
(y el motor queda atado a esa carpeta: no la muevas ni la borres, o vuelve a correr el
instalador); **Git** hay que pedírselo a TI y volver a correr el instalador.

### Si falta la carpeta Data BI

El resumen puede decir que falta el acceso directo a "Data BI - Datos" (el stock que
sube el equipo cada mañana). No frena nada, pero conviene agregarlo:

1. En el navegador, abre el sitio de SharePoint **Abastecimiento y Logística - Data BI**.
2. Entra a **Documentos > Data BI > Datos** y elige **Agregar acceso directo a Mis archivos**.
3. En el Explorador, dentro de `OneDrive - Curifor S.A`, clic derecho sobre la carpeta
   nueva y **Mantener siempre en este dispositivo**.

## El día del cambio

1. Un admin entra a la plataforma, **Cargar > Fuentes de datos**, y deja tu PC como
   **titular**. Hasta entonces tu PC no publica.
2. Ese mismo día, en el PC del dueño, se deshabilitan sus tareas (ver
   `apps/api/data/crudos/README.md`, "Cambio de PC titular").
3. Entra a la plataforma (Portada, o Cargar datos si eres admin), aprieta **Actualizar ahora** y
   revisa que la tarjeta termine en **Listo**. Tarda entre 25 y 40 minutos.

## Todos los días hábiles

1. **Baja las tablas del ERP** con tu programa. Mientras hace clics en Flexline, no toques
   el mouse ni el teclado (unos 9 minutos).
2. Cuando termine, aprieta **Actualizar ahora** en la Portada (o en Cargar datos, si eres
   admin). La tarjeta
   muestra el avance y termina en **Listo**. Tarda entre 25 y 40 minutos.
3. Puedes seguir usando el PC, pero no lo apagues ni lo suspendas hasta que termine.

Lo que tiene que cumplir tu PC en el momento de apretar:

- **Prendido, sin suspender y con tu sesión iniciada.** Si no, a los 5 minutos la tarjeta
  dice "Nadie tomó la solicitud": inicia sesión (o despierta el PC) y vuelve a apretar.
  Si se reinició de madrugada (pasa a la 01:00), inicia sesión antes de apretar.
- **Tablas al día.** Si algún archivo lleva demasiado sin actualizarse, el motor no
  publica nada y la tarjeta dice cuáles son. De fábrica el límite es de 2 días hábiles
  para el stock y el seguimiento nacional, y de 7 para los otros seguimientos (se ve y se
  cambia en Cargar > Fuentes de datos); los feriados no se descuentan. Baja las tablas y
  vuelve a apretar.

Además:

- **Actualizar motor** (solo admin, en Cargar) baja la última versión del motor sin
  recalcular nada.
- Cada mes hay que dejar el respaldo de ventas en `Bases de datos\Ventas`
  (`apps/api/data/crudos/README.md`, "El paso de cada mes").

## Si algo falla

- El mensaje de la ventana o de la tarjeta de la web dice el motivo y qué hacer.
- Los registros quedan en `%USERPROFILE%\dev\Sugerencia-SaaS-para-sucursales\logs`:
  `motor_<fecha>.log` (cálculo del día) y `agente_<fecha>.log` (botones de la web).
- Ante la duda, vuelve a correr `INSTALAR PLATAFORMA.cmd`: revisa todo y arregla lo que
  falte.

## Para quien mantiene el motor

- El instalador es `scripts/instalar_pc_jefa.ps1`; el `.cmd` de la raíz lo corre, y
  suelto lo baja de GitHub (rama `arreglar-job-diario`), así que esa rama tiene que
  tener este instalador publicado.
- Deja una sola tarea de Windows, `Sugerido Curifor - Agente` (al iniciar sesión y cada
  minuto, con la sesión iniciada, a través de `scripts/sin_ventana.vbs` para no abrir
  ventanas; si el PC no permite VBScript usa PowerShell oculto). No registra la de las
  09:30 ni la de al iniciar sesión: el motor solo corre cuando el agente toma un pedido
  del botón. Esas dos y `tarea_si_no_corrio_hoy.ps1` son del PC del dueño hasta el día
  del cambio.
- No toca el programa del ERP: no lo copia, no lo borra ni lo anota en el `.env`. Solo
  mira las carpetas de su kit para usar su Python portable si el PC no deja instalar
  Python.
- `-Simular` hace todo en `%TEMP%\simulacion-instalador`: sin instalar programas, sin
  claves (valores ficticios), sin la plataforma de verdad (`http://127.0.0.1:8765`) y con
  la tarea registrada como `PRUEBA-...`, deshabilitada, y borrada al final.
  `-SimularSinCarpetas` muestra los avisos de carpetas faltantes. Las pruebas están en
  `apps/api/tests_motor/test_instalador_pc.py`.
- El código se clona con `http.sslBackend=schannel` y queda así en la configuración del
  repositorio: la red de la empresa revisa las conexiones seguras con un certificado que
  Windows conoce y OpenSSL no. El agente usa lo mismo en "Actualizar motor".
- Al final el instalador deja guardada la configuración de Fuentes de datos
  (`python -m src.motor.config_fuentes --guardar-config`): sin ella, si la plataforma no
  respondía en la primera corrida, el PC nuevo se creía titular y publicaba.
- Cuando el motor frena por archivos faltantes o viejos, el agente arma el mensaje de la
  tarjeta con los archivos del bloque "Archivos vencidos:" (o "Problemas:") que imprime
  el motor (`Archivos-Frenados`, en `scripts/salida_motor.ps1`).
