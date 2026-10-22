# ADR 0004 — Fuentes de datos sin TI: carpetas sincronizadas y configuración en la plataforma

**Estado:** Aceptado · **Fecha:** 2026-10-16

## Contexto

El motor corre a las 09:30 de cada día hábil en un PC con una tarea de Windows. Lee
archivos Excel de carpetas que OneDrive mantiene sincronizadas, calcula el sugerido
y lo publica en la plataforma.

Hasta ahora sabía qué archivo leer por dos variables del `.env` de ese PC
(`MOTOR_CRUDOS_DIR` y `MOTOR_STOCK_DIR`) y por patrones de nombre escritos en
`apps/api/src/motor/fuentes.py`. Eso tuvo tres problemas:

- Un archivo nuevo en la carpeta botó la corrida diaria tres veces.
- Nadie podía ver qué archivo leyó el motor ni de qué fecha era.
- La configuración vivía en un solo PC. El dueño actual deja la empresa y la jefa
  queda a cargo; el programa que baja las tablas del ERP ya corre en su PC.

## Decisión

1. **Sin TI.** No se registran apps en Microsoft 365, no se usa Microsoft Graph y no
   se lee el registro de Windows. El motor lee carpetas locales que OneDrive
   sincroniza: la carpeta de OneDrive de la empresa (`%OneDriveCommercial%`) y los
   accesos directos a bibliotecas de SharePoint que aparecen dentro de ella.
2. **Un PC prendido corre el motor.** Es el "PC titular" y se elige en el panel. Una
   corrida oficial en otro PC no calcula ni publica: solo informa qué encontraría.
3. **La configuración vive en la plataforma** (pantalla de admin "Fuentes de datos"):
   por fuente, la carpeta portable y la subcarpeta, cómo se elige el archivo, cada
   cuánto debe actualizarse, si frena o solo avisa y si es obligatoria. Las rutas se
   guardan sin el usuario de Windows (`%OneDriveCommercial%\…`), así sirven en
   cualquier PC.
4. **Preparado para otras empresas.** Todo lleva `tenant_id` y ni el modelo ni las
   reglas nombran a Curifor. El catálogo de fuentes lo declara el motor (qué fuentes
   existen, cuáles son requeridas, qué plazos mínimos tienen) y la plataforma valida
   contra él. El multiempresa no se construye ahora.
5. **El motor nunca deja de correr por culpa de esto.** La configuración se pide al
   partir, con una cascada:
   - `MOTOR_FUENTES=env` en el `.env` del PC: se usa el `.env` y no se le pide la
     configuración a la plataforma (tampoco se mira el PC titular). El reporte al
     panel se sigue mandando, así el panel muestra que corrió con la del PC.
   - La plataforma responde: se usa y se guarda en `apps/api/data/fuentes_config_cache.json`.
   - No responde o manda algo inválido: se usa la guardada, por vieja que sea.
   - No hay guardada: se usa el `.env`, como siempre.

   Solo los errores al traer la configuración activan la cascada. Un archivo que no
   se puede copiar o leer queda como estado de su fuente.
6. **Tres modos, para desplegar sin riesgo.**
   - `sin_configurar` (el día del deploy): el motor usa el `.env` y manda en cada
     reporte lo que usa hoy, para sembrar la configuración con un botón.
   - `prueba`: el motor sigue usando el `.env` y además compara con la configuración
     de la plataforma. Lo que se publica no cambia.
   - `activa`: el motor usa la configuración de la plataforma. Una fuente obligatoria
     que falta, un stock que llega vacío o dos fuentes con el mismo archivo frenan la
     publicación con un motivo claro.
7. **Una sola versión de cada archivo por corrida.** El motor copia los archivos
   elegidos a `apps/api/data/corrida/<id>/` y todos los pasos leen la copia. Si
   OneDrive reemplaza el stock a mitad de corrida, el sugerido y la lista de precios
   siguen leyendo lo mismo.

## Consecuencias

- (+) El panel muestra qué archivo leyó cada fuente, de qué carpeta, con qué fecha y
  cuántas filas, y avisa cuando algo se atrasa, falta o llega vacío.
- (+) Cambiar de PC titular o mover una fuente a SharePoint se hace desde el panel,
  primero como ensayo en prueba.
- (+) Sin TI no hay permisos que pedir ni secretos nuevos: el motor entra con el
  mismo usuario admin con que ya publica.
- (−) Depende de que el PC titular esté prendido, con la sesión abierta y con
  OneDrive sincronizando. El panel lo hace visible ("El PC titular no corrió hoy",
  "OneDrive cerrado"), pero no lo resuelve.
- (−) Un archivo que vive en el OneDrive personal de alguien deja de existir cuando
  se cierra esa cuenta. Las fuentes tienen que quedar en carpetas que el PC titular
  vea con su propia cuenta.
- (−) La URL del sitio de SharePoint de un acceso directo no se puede deducir desde
  el PC sin leer el registro: al sembrar queda en blanco y la completa un admin.
- Fases siguientes (no se construyen ahora): subir archivos desde la web, mapeo de
  columnas, leer SharePoint por la nube con Graph (requiere TI) o un motor en la
  nube, y resolver carpetas por el registro de OneDrive.
