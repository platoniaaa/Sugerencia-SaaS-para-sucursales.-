# Llevar la plataforma a producción (nube, sin login)

Objetivo: que los trabajadores de Curifor abran un link y vean los datos actualizados.
Tú actualizas los datos desde tu PC (Power BI Desktop) con un clic.

```
Tu PC (Power BI) ──push──► Supabase (base de datos en la nube)
                                  │
        Vercel (web pública) ◄── Render (backend) ◄── lee de Supabase
                  ▲
   Trabajadores abren el link
```

> ⚠️ Sin login, **cualquiera con el link ve los datos**. Si quieres, agregamos un código de
> acceso compartido (1 clave para todos). Pídelo y lo activo.

---

## Paso 0 — Subir el código a GitHub (requisito)

Vercel y Render despliegan desde un repositorio de GitHub.

1. Crea una cuenta en https://github.com y un repositorio nuevo (privado), ej. `sugerido-compras`.
2. En la carpeta del proyecto:
   ```powershell
   git init
   git add .
   git commit -m "Plataforma sugerido de compras"
   git branch -M main
   git remote add origin https://github.com/<tu-usuario>/sugerido-compras.git
   git push -u origin main
   ```

## Paso 1 — Base de datos: Supabase

1. Crea cuenta en https://supabase.com → **New project** (elige región cercana, ej. São Paulo).
   Anota la **Database password** que defines.
2. En el proyecto → **Connect** (o Project Settings → Database) → copia la cadena de conexión.
3. Ármala en formato pg8000 (reemplaza usuario, clave y host con los tuyos):
   ```
   postgresql+pg8000://postgres.xxxx:TU_CLAVE@aws-0-...pooler.supabase.com:5432/postgres
   ```
   (Usa el **Session pooler**, puerto 5432.)

## Paso 2 — Backend: Render

1. Crea cuenta en https://render.com → **New** → **Blueprint** → conecta tu repo de GitHub.
   Render detecta el archivo `render.yaml` y crea el servicio `sugerido-api`.
   (Alternativa manual: **New → Web Service**, Root Directory `apps/api`,
   Build `pip install -r requirements.txt`,
   Start `uvicorn src.main:app --host 0.0.0.0 --port $PORT`.)
2. En **Environment** del servicio, agrega:
   - `DATABASE_URL` = la cadena de Supabase del Paso 1.
   - `CORS_ORIGINS` = (lo llenas en el Paso 4 con la URL de Vercel; por ahora `*`).
3. Deploy. Cuando termine, copia la URL del backend, ej. `https://sugerido-api.onrender.com`.
   Pruébala: `https://sugerido-api.onrender.com/api/health` debe responder `{"status":"ok"}`.

## Paso 3 — Frontend: Vercel

1. Crea cuenta en https://vercel.com → **Add New → Project** → importa tu repo de GitHub.
2. En la configuración del proyecto:
   - **Root Directory**: `apps/web`
   - **Environment Variables**: `NEXT_PUBLIC_API_URL` = la URL de Render del Paso 2.
3. Deploy. Vercel te da la URL pública, ej. `https://sugerido-compras.vercel.app`.
   **Ese es el link que les pasas a los trabajadores.**

## Paso 4 — Conectar frontend y backend (CORS)

1. Vuelve a Render → variable `CORS_ORIGINS` = la URL de Vercel (ej. `https://sugerido-compras.vercel.app`).
2. Render redepliega. Listo: la web ya habla con el backend.

## Paso 5 — Cargar los datos (desde tu PC)

1. En la **raíz del proyecto en tu PC**, crea el archivo `.env` (copia de `.env.example`) y pon:
   ```
   DATABASE_URL=postgresql+pg8000://postgres.xxxx:TU_CLAVE@...pooler.supabase.com:5432/postgres
   ```
   (la misma cadena de Supabase del Paso 1).
2. Abre **Power BI Desktop** con tu modelo del sugerido.
3. Doble clic a **`scripts\push_to_cloud.ps1`**.
   Eso lee el Power BI y sube los datos a Supabase. Los trabajadores los ven al instante.
4. Repite el paso 3 cada vez que quieras actualizar (ej. cada mañana).
   - Para automatizarlo: Programador de tareas de Windows apuntando a `push_to_cloud.ps1`.

## Costos

- Supabase: free para empezar (Pro USD 25/mes si crece).
- Render: free (el servicio "duerme" tras inactividad; la 1ª carga tarda ~30s). Plan pago ~USD 7/mes evita el sleep.
- Vercel: free (Hobby).

## Cuando consigas un admin de Microsoft 365

- **Login con cuenta corporativa**: se agrega con Supabase Auth + proveedor Entra ID.
- **Datos 100% automáticos** (sin tu PC): el service principal de Power BI que ya está
  construido (`docs/powerbi-sync.md`) corre en la nube en un horario.

## Resumen de qué hace cada quién

| Quién | Qué |
|---|---|
| Trabajadores | Abren la URL de Vercel y ven los datos. Nada que instalar. |
| Tú (Francisco) | 1 clic a `push_to_cloud.ps1` para actualizar (con Power BI abierto). |
| La nube | Mantiene la web y la base disponibles 24/7. |
