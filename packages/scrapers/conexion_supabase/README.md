# Tutorial para subir CSV de scrapers a Supabase

Este documento es únicamente para las personas que van a **recibir credenciales limitadas** y necesitan subir archivos `.csv` al proyecto de Supabase.

No necesitas permisos de administrador.  
No necesitas crear tablas.  
No necesitas modificar políticas RLS.  
No debes usar llaves maestras.

---

## 1. Qué vas a hacer

El flujo es este:

```text
CSV del scraper
  ↓
script de carga
  ↓
login con usuario limitado de Supabase
  ↓
subida a raw.social_scraping_uploads
  ↓
verificación de carga
```

El objetivo es que puedas subir archivos CSV de redes sociales como:

```text
X / Twitter
Facebook
TikTok
Otra fuente autorizada del proyecto
```

---

## 2. Antes de pedir credenciales: información que debes enviar

Antes de que se te entregue un usuario de ingesta, debes enviar una descripción corta del archivo CSV que vas a subir.

Esto no es para que tú crees tablas ni modifiques Supabase. Es para que la persona encargada de permisos pueda validar la fuente, revisar riesgos de privacidad y confirmar que tu carga va al lugar correcto.

Debes enviar:

```text
1. Fuente de datos:
   X / Twitter, Facebook, TikTok u otra.

2. Responsable:
   Nombre de la persona o equipo que sube el CSV.

3. Objetivo del archivo:
   Para qué se recolectaron esos datos.

4. Nombre esperado del archivo:
   Ejemplo: tweets_elecciones_parlamentarias_2026.csv

5. Cantidad aproximada de filas:
   Ejemplo: 500, 5.000, 20.000.

6. Columnas del CSV:
   Lista de nombres de columnas.

7. Muestra de 3 a 5 filas:
   Puede ser una muestra anonimizada si contiene datos sensibles.

8. Tipo de datos sensibles:
   Indicar si contiene usuarios, nombres, links, ubicación, texto de publicaciones,
   comentarios, identificadores, fechas, imágenes u otros datos relevantes.

9. Frecuencia de carga:
   Una sola vez, diaria, semanal, por entrega, etc.

10. Tipo de operación:
   Carga nueva, actualización de un archivo anterior o reemplazo.
```

Formato sugerido para enviar esta información:

```text
Fuente: X / Twitter
Responsable: Equipo Desarrollo
Objetivo: Recolectar publicaciones sobre elecciones parlamentarias.
Archivo: tweets_elecciones_parlamentarias_2026.csv
Filas aproximadas: 500
Columnas: tweet_id, text, author_username, created_at, likes, reposts, replies, url
Muestra: adjunto CSV con 5 filas de ejemplo
Datos sensibles: usernames, texto público, URLs
Frecuencia: carga única
Operación: carga nueva
```

---

## 3. Cómo funciona la tabla de carga

Para este proyecto se usa una tabla genérica de aterrizaje:

```text
raw.social_scraping_uploads
```

Esto significa que no necesitas que exista una tabla diferente para cada CSV.

Cada fila de tu CSV se guarda dentro de una columna llamada:

```text
payload
```

`payload` almacena la fila completa en formato JSON.

Ejemplo: si tu CSV tiene esto:

```csv
post_id,text,author,created_at,likes
x_001,Texto de prueba,usuario1,2026-01-01T10:00:00Z,10
```

En Supabase se guarda algo así:

```json
{
  "post_id": "x_001",
  "text": "Texto de prueba",
  "author": "usuario1",
  "created_at": "2026-01-01T10:00:00Z",
  "likes": "10"
}
```

Por eso, normalmente no necesitas esperar a que se cree una tabla específica para tu CSV. Sin embargo, sí debes informar su estructura antes de subirlo para control de privacidad, trazabilidad y posterior transformación de datos.

---

## 4. Qué credenciales debes recibir

La persona encargada de permisos te debe entregar estos datos:

```env
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_AUTH_EMAIL=
SUPABASE_AUTH_PASSWORD=
SUPABASE_SCHEMA=raw
SUPABASE_TABLE=social_scraping_uploads
SOURCE=
```

Ejemplo para X/Twitter:

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=sb_publishable_xxxxxxxxxxxxxxxxx
SUPABASE_AUTH_EMAIL=x.ingestor@datos-electorales.local
SUPABASE_AUTH_PASSWORD=contraseña_asignada
SUPABASE_SCHEMA=raw
SUPABASE_TABLE=social_scraping_uploads
SOURCE=x
```

Ejemplo para Facebook:

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=sb_publishable_xxxxxxxxxxxxxxxxx
SUPABASE_AUTH_EMAIL=facebook.ingestor@datos-electorales.local
SUPABASE_AUTH_PASSWORD=contraseña_asignada
SUPABASE_SCHEMA=raw
SUPABASE_TABLE=social_scraping_uploads
SOURCE=facebook
```

---

## 5. Qué NO debes recibir ni usar

No debes usar ninguna variable como estas:

```env
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_SECRET_KEY=
DATABASE_URL=
JWT_SECRET=
```

Si alguien te pide pegar una `service_role_key` en tu `.env`, avisa al equipo de arquitectura o a la persona encargada de permisos. Para este flujo solo se debe usar:

```env
SUPABASE_ANON_KEY
SUPABASE_AUTH_EMAIL
SUPABASE_AUTH_PASSWORD
```

---

## 6. Diferencia importante: usuario del script vs. acceso al dashboard

Las credenciales que recibes para subir datos son credenciales de **Supabase Auth**. Sirven para que el script inicie sesión y cargue datos.

Eso no siempre significa que puedas entrar al panel web de Supabase como administrador.

Puedes tener:

```text
Correo y contraseña para el script de carga: sí
Permisos de administrador en Supabase Dashboard: no
```

Esto es intencional. El objetivo es permitir la ingesta sin dar acceso total al proyecto.

---

## 7. Preparar el repositorio

Abre PowerShell y ubícate donde tienes el proyecto:

```powershell
cd C:\Users\paula\Desktop\DatosElectorales
```

Actualiza el repo:

```powershell
git pull origin main
```

Verifica que exista esta carpeta:

```powershell
dir packages\scrapers\conexion_supabase
```

Debes ver al menos estos archivos:

```text
README.md
upload_social_csv_to_supabase.py
examples
```

---

## 8. Crear y activar entorno virtual

Desde la raíz del repo:

```powershell
python -m venv .venv
```

Activa el entorno:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación, ejecuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Instala dependencias:

```powershell
python -m pip install --upgrade pip
python -m pip install supabase python-dotenv pandas
```

---

## 9. Crear el archivo `.env`

Desde la raíz del repo:

```powershell
notepad .env
```

Pega las credenciales que te entregaron.

Ejemplo para X/Twitter:

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=sb_publishable_xxxxxxxxxxxxxxxxx
SUPABASE_AUTH_EMAIL=x.ingestor@datos-electorales.local
SUPABASE_AUTH_PASSWORD=contraseña_asignada

SUPABASE_SCHEMA=raw
SUPABASE_TABLE=social_scraping_uploads
SOURCE=x
CSV_PATH=packages/scrapers/conexion_supabase/examples/test_x.csv
BATCH_SIZE=500
```

Ejemplo para Facebook:

```env
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=sb_publishable_xxxxxxxxxxxxxxxxx
SUPABASE_AUTH_EMAIL=facebook.ingestor@datos-electorales.local
SUPABASE_AUTH_PASSWORD=contraseña_asignada

SUPABASE_SCHEMA=raw
SUPABASE_TABLE=social_scraping_uploads
SOURCE=facebook
CSV_PATH=packages/scrapers/conexion_supabase/examples/test_facebook.csv
BATCH_SIZE=500
```

Guarda y cierra.

---

## 10. Verificar que el `.env` no se suba a Git

Ejecuta:

```powershell
git status
```

Si aparece `.env`, no lo subas.

Verifica si está ignorado:

```powershell
git check-ignore -v .env
```

Si no aparece nada, agrega `.env` al `.gitignore`:

```powershell
Add-Content -Path ".\.gitignore" -Value "`n.env"
```

Vuelve a verificar:

```powershell
git check-ignore -v .env
```

---

## 11. Hacer una primera prueba con CSV de ejemplo

### 11.1. Prueba para X/Twitter

Configura temporalmente estas variables en PowerShell:

```powershell
$env:SOURCE="x"
$env:CSV_PATH="packages/scrapers/conexion_supabase/examples/test_x.csv"
```

Ejecuta:

```powershell
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

### 11.2. Prueba para Facebook

Configura:

```powershell
$env:SOURCE="facebook"
$env:CSV_PATH="packages/scrapers/conexion_supabase/examples/test_facebook.csv"
```

Ejecuta:

```powershell
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

---

## 12. Salida esperada

Si todo está bien, deberías ver algo parecido a esto:

```text
[step] Reading CSV...
[csv] packages/scrapers/conexion_supabase/examples/test_x.csv: 2 rows loaded
[csv] source=x
[step] Connecting to Supabase...
[auth] Login OK as: x.ingestor@datos-electorales.local
[auth] User UID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[auth] Schema: raw
[auth] Table: social_scraping_uploads
[run] RUN_ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[step] Uploading rows...
[upload] 2/2 rows uploaded
[done] Upload finished
[done] Rows uploaded: 2
[done] RUN_ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
[verify] Rows visible to this user for this RUN_ID: 2
```

Guarda el `RUN_ID`. Ese código identifica tu carga.

---

## 13. Subir un CSV real

Cuando ya tengas tu CSV real del scraper, solo debes cambiar `CSV_PATH` y `SOURCE`.

Ejemplo para X/Twitter:

```powershell
$env:SOURCE="x"
$env:CSV_PATH="packages/scrapers/twitter/tweets_elecciones.csv"
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

Ejemplo para Facebook:

```powershell
$env:SOURCE="facebook"
$env:CSV_PATH="packages/scrapers/facebook/facebook_posts.csv"
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

También puedes dejarlo fijo en el `.env`:

```env
SOURCE=x
CSV_PATH=packages/scrapers/twitter/tweets_elecciones.csv
```

y ejecutar simplemente:

```powershell
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

---

## 14. Cómo debe estar el CSV

El CSV debe tener encabezados en la primera fila.

Ejemplo válido:

```csv
post_id,text,author,created_at,likes,comments
x_001,Texto de prueba,usuario1,2026-01-01T10:00:00Z,10,2
x_002,Segundo texto,usuario2,2026-01-01T10:05:00Z,5,1
```

No importa si el CSV de X tiene columnas distintas al de Facebook. El script guarda cada fila como JSON dentro de `payload`.

---

## 15. Qué datos se guardan en Supabase

Cada fila del CSV se guarda en:

```text
raw.social_scraping_uploads
```

Con esta estructura:

| Campo | Significado |
|---|---|
| `id` | Identificador interno |
| `run_id` | Identificador de la carga |
| `source` | Fuente: `x`, `facebook`, `tiktok`, etc. |
| `original_filename` | Nombre del CSV cargado |
| `row_number` | Número de fila dentro del CSV |
| `payload` | Fila completa del CSV en formato JSON |
| `uploaded_by` | Usuario que hizo la carga |
| `created_at` | Fecha/hora de subida |

---

## 16. Verificar en Supabase si te dieron acceso al panel

Si además de las credenciales del script te dieron acceso visual al proyecto de Supabase:

1. Entra a Supabase.
2. Abre el proyecto.
3. Ve a **Table Editor**.
4. Busca el schema `raw`.
5. Abre la tabla:

```text
social_scraping_uploads
```

6. Filtra por tu `run_id`.

Si no tienes acceso al panel, no pasa nada. La carga se valida desde la salida del script con:

```text
[verify] Rows visible to this user for this RUN_ID: N
```

---

## 17. Qué debes reportar después de subir un CSV

Después de cada carga, reporta esto al equipo:

```text
Fuente:
Archivo:
Cantidad de filas:
RUN_ID:
Usuario usado:
Fecha/hora aproximada:
Observaciones:
```

Ejemplo:

```text
Fuente: x
Archivo: tweets_elecciones_parlamentarias_2026.csv
Cantidad de filas: 500
RUN_ID: 7f18d1e2-4d9b-4df7-b2f0-f7309a91d23e
Usuario usado: x.ingestor@datos-electorales.local
Fecha/hora aproximada: 2026-05-10 18:30
Observaciones: carga exitosa
```

---

## 18. Errores comunes

### 18.1. `Invalid login credentials`

Significa que el correo o la contraseña están mal.

Revisa:

```env
SUPABASE_AUTH_EMAIL=
SUPABASE_AUTH_PASSWORD=
```

Si el problema continúa, pide a la persona encargada de permisos que cambie la contraseña.

---

### 18.2. `PGRST205: Could not find the table`

Significa que la API no encuentra la tabla.

Reporta el error a la persona encargada de permisos. Puede faltar exponer el schema o recargar caché.

---

### 18.3. `permission denied for schema raw`

Tu usuario no tiene permiso para usar el schema `raw`.

Reporta el error a la persona encargada de permisos.

---

### 18.4. `new row violates row-level security policy`

Tu usuario inició sesión, pero no está autorizado por la política RLS para insertar.

Reporta el error y envía el correo usado:

```env
SUPABASE_AUTH_EMAIL=
```

---

### 18.5. `No existe el CSV`

Ejemplo:

```text
FileNotFoundError: No existe el CSV
```

Significa que `CSV_PATH` está mal.

Verifica la ruta:

```powershell
dir packages\scrapers\twitter
```

o copia la ruta exacta del archivo.

---

### 18.6. El CSV no tiene encabezados

El archivo debe tener nombres de columnas en la primera fila.

Incorrecto:

```csv
x_001,Texto,usuario1
x_002,Texto 2,usuario2
```

Correcto:

```csv
post_id,text,author
x_001,Texto,usuario1
x_002,Texto 2,usuario2
```

---

## 19. Comandos rápidos

### X/Twitter

```powershell
cd C:\Users\paula\Desktop\DatosElectorales
.\.venv\Scripts\Activate.ps1
$env:SOURCE="x"
$env:CSV_PATH="packages/scrapers/twitter/tweets_elecciones.csv"
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

### Facebook

```powershell
cd C:\Users\paula\Desktop\DatosElectorales
.\.venv\Scripts\Activate.ps1
$env:SOURCE="facebook"
$env:CSV_PATH="packages/scrapers/facebook/facebook_posts.csv"
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

### CSV de prueba

```powershell
cd C:\Users\paula\Desktop\DatosElectorales
.\.venv\Scripts\Activate.ps1
$env:SOURCE="test"
$env:CSV_PATH="packages/scrapers/conexion_supabase/examples/test_x.csv"
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```

---

## 20. Reglas de seguridad

1. No compartas tu `.env`.
2. No subas `.env` a GitHub.
3. No uses `service_role_key`.
4. No modifiques tablas ni permisos.
5. No borres datos en Supabase.
6. Reporta el `RUN_ID` de cada carga.
7. Usa únicamente CSV autorizados por el proyecto.
8. Si ves datos sensibles, avisa al equipo de privacidad/ética.

---

## 21. Resumen final

Para subir un CSV necesitas:

```text
1. Enviar primero la estructura esperada del CSV.
2. Recibir credenciales limitadas.
3. Configurar el .env.
4. Tener un CSV con encabezados.
5. Ejecutar upload_social_csv_to_supabase.py.
6. Guardar y reportar el RUN_ID.
```

Comando principal:

```powershell
python packages\scrapers\conexion_supabase\upload_social_csv_to_supabase.py
```
