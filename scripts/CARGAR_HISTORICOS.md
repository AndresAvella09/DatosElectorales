# Carga de CSV históricos al pipeline

Script: `scripts/cargar_historicos.ps1`

Sube cualquier CSV de redes sociales a Supabase pasando por las tres capas del pipeline: **Bronze → Silver → Gold**.

---

## Requisitos

- `uv` instalado
- Archivo `.env` en la raíz del proyecto con `SUPABASE_URL` y `SUPABASE_KEY`

---

## Uso

### Modo interactivo (recomendado)

```powershell
.\scripts\cargar_historicos.ps1
```

1. Se abre el explorador de Windows — seleccionas el CSV
2. El script detecta la fuente por el nombre del archivo automáticamente
3. Si no puede detectarla, te pregunta con un menú en consola
4. Corre el pipeline completo y muestra el resultado

### Modo con argumentos

```powershell
.\scripts\cargar_historicos.ps1 -Csv "ruta\al\archivo.csv" -Fuente tiktok
```

| Parámetro | Descripción | Obligatorio |
|---|---|---|
| `-Csv` | Ruta al CSV a subir | No (abre el selector si se omite) |
| `-Fuente` | `facebook` / `tiktok` / `youtube` / `twitter` | No (se autodetecta si se omite) |
| `-SubirStorage` | Guarda el CSV crudo en el bucket `bronze-raw` | No (off por defecto) |

---

## Detección automática de fuente

El script infiere la fuente a partir del nombre del archivo:

| Palabras clave en el nombre | Fuente detectada |
|---|---|
| `facebook`, `fb_` | `facebook` |
| `tiktok`, `tk_` | `tiktok` |
| `youtube`, `yt_` | `youtube` |
| `tweet`, `twitter`, `tw_` | `twitter` |

Si el nombre no contiene ninguna de esas palabras, el script te pregunta:

```
  No se pudo detectar la fuente desde el nombre: 'mis_datos.csv'
  Elige la fuente:
    [1] facebook
    [2] tiktok
    [3] youtube
    [4] twitter
  Opcion (1-4):
```

---

## Qué hace con los datos

```
CSV  →  Bronze (raw.posts)  →  Silver (limpieza + anonimización)  →  Gold
```

| Etapa | Qué ocurre |
|---|---|
| **Bronze** | Parsea el CSV, genera IDs únicos por fuente y sube a `raw.posts` |
| **Silver** | Normaliza texto, quita URLs / @menciones / #hashtags, detecta idioma, anonimiza usuarios |
| **Gold** | Agrega features para análisis (sentimiento, engagement normalizado, etc.) |

### Garantías anti-duplicados

| Nivel | Mecanismo |
|---|---|
| **Archivo completo** | sha256 del CSV — si ya fue subido antes, se salta sin error |
| **Fila en Bronze** | `UPSERT ON CONFLICT id` en `raw.posts` |
| **Fila en Silver** | Verifica IDs existentes; solo escribe los que son nuevos |

El script **no mueve ni borra** el CSV original (`--no-archive`).

---

## Ejemplos rápidos

```powershell
# Subir un CSV de TikTok sin dialogo
.\scripts\cargar_historicos.ps1 -Csv "data\todos\todos datos proyecto elecciones\tiktok_comments.csv" -Fuente tiktok

# Subir un CSV y además guardar el archivo crudo en Storage
.\scripts\cargar_historicos.ps1 -SubirStorage

# Subir un CSV con nombre genérico (te preguntará la fuente)
.\scripts\cargar_historicos.ps1 -Csv "C:\Descargas\export_final_v2.csv"
```

---

## Salida esperada

```
==> Archivo seleccionado: tiktok_comments.csv
    ... Fuente detectada automaticamente: tiktok
    ... Storage: no (solo DB)

==> Corriendo pipeline Bronze -> Silver -> Gold...
    $ uv run python -m data_pipeline.loaders.cli e2e --csv ... --source tiktok --no-archive

    OK  Pipeline completado para 'tiktok_comments.csv' (fuente: tiktok)
```

Si el archivo ya fue subido anteriormente:

```
    OK e2e run_id=... (0 filas - posible duplicado por sha)
```
