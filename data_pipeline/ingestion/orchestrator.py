"""
orchestrator.py — Coordinador que ejecuta scrapers y deposita resultados en Bronze.

QUÉ HACE ESTE SCRIPT                                         
1. Lee los CSVs generados por cada scraper (Twitter, YouTube) o datos externos
2. Mapea las columnas de cada fuente al esquema unificado    
   RawSocialPost (contrato Bronze)                           
3. Almacena los registros en data/bronze/ particionados por  
   fuente y fecha de ingestión                               

Importante:
    - NO ejecuta los scrapers directamente. Cada scraper se ejecuta
      de forma independiente según sus propias instrucciones (ver howToUse).
    - Este script solo RECOGE los CSVs ya generados y los normaliza.

Mapeo de columnas por fuente:
    Twitter → RawSocialPost:
        id          → "tw_{id}"
        Query       → metadata.query
        datetime    → datetime_utc
        username    → username
        content     → text
        replies     → engagement.replies
        retweets    → engagement.retweets
        likes       → engagement.likes

    YouTube → RawSocialPost:
        id          → (ya tiene prefijo "yt_")
        parent_id   → parent_id
        date        → datetime_utc
        text        → text
        username    → username
        likes       → engagement.likes
        views       → engagement.views
        video_id    → metadata.video_id
        video_title → metadata.video_title
        query       → metadata.query

    External (Genérico) → RawSocialPost:
        id          → "ext_{id}" o UUID generado
        text        → text/content/mensaje/body
        date        → datetime_utc (desde date/datetime/fecha)
        username    → username/author/usuario
        metadata    → import_source: "external_csv"

Uso:
    uv run python data-pipeline/ingestion/orchestrator.py \
        --twitter-csv packages/scrapers/twitter/tweets_colombia.csv \
        --youtube-csv packages/scrapers/youtube/youtube_data.csv \
        --external-csv ruta/a/datos_externos.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

import pandas as pd

# Agregar la raíz del proyecto al path para imports locales
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.bronze import RawSocialPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("ingestion.orchestrator")


# ── Utilidades ────────────────────────────────────────────────────

def _sv(v: object, default: str = "") -> str:
    """Convierte valor de pandas a str, tratando NaN/None como default."""
    if v is None:
        return default
    s = str(v)
    return default if s in ("nan", "None") else s


def _iv(v: object) -> int | None:
    """Convierte valor de pandas a int, devuelve None para NaN/None."""
    if v is None or str(v) in ("nan", "None", ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ── Mapeadores por fuente ──────────────────────────────────────────


def _map_twitter_row(row: dict) -> RawSocialPost:
    """Mapea una fila de CSV de Twitter al esquema Bronze."""
    tweet_id = _sv(row.get("id")).replace(".0", "")
    engagement = {
        k: _iv(row.get(k))
        for k in ("replies", "retweets", "likes")
        if _iv(row.get(k)) is not None
    }
    query = _sv(row.get("Query", row.get("query", "")))
    return RawSocialPost(
        id=f"tw_{tweet_id}",
        source="twitter",
        source_id=tweet_id,
        datetime_utc=_sv(row.get("datetime")) or None,
        username=_sv(row.get("username")) or None,
        text=_sv(row.get("content")),
        parent_id=None,
        engagement=engagement,
        metadata={"query": query} if query else {},
    )


def _map_youtube_row(row: dict) -> RawSocialPost:
    """Mapea una fila de CSV de YouTube al esquema Bronze."""
    raw_id = _sv(row.get("id"))
    yt_id = raw_id if raw_id.startswith("yt_") else f"yt_{raw_id}"
    source_id = raw_id.replace("yt_", "", 1)
    parent_id = _sv(row.get("parent_id")) or None

    engagement = {k: _iv(row.get(k)) for k in ("likes", "views") if _iv(row.get(k)) is not None}
    metadata = {k: _sv(row.get(k)) for k in ("video_id", "video_title", "query") if _sv(row.get(k))}

    return RawSocialPost(
        id=yt_id,
        source="youtube",
        source_id=source_id,
        datetime_utc=_sv(row.get("date")) or None,
        username=_sv(row.get("username")) or None,
        text=_sv(row.get("text")),
        parent_id=parent_id,
        engagement=engagement,
        metadata=metadata,
    )


def _map_tiktok_row(row: dict) -> RawSocialPost:
    """Mapea una fila de tiktok_comments al esquema Bronze.

    Esperado del scraper packages/scrapers/tiktok/scrape_tiktok.py:
        video_id, comment_id, create_time, user_unique_id, user_nickname,
        text, digg_count, reply_count
    """
    raw_id = _sv(row.get("comment_id"))
    if not raw_id:
        raise ValueError("tiktok row sin comment_id")
    tk_id = raw_id if raw_id.startswith("tk_") else f"tk_{raw_id}"

    engagement = {
        k: _iv(row.get(src))
        for k, src in (("likes", "digg_count"), ("replies", "reply_count"))
        if _iv(row.get(src)) is not None
    }
    video_id = _sv(row.get("video_id"))

    return RawSocialPost(
        id=tk_id,
        source="tiktok",
        source_id=raw_id,
        datetime_utc=_sv(row.get("create_time")) or None,
        username=_sv(row.get("user_unique_id")) or _sv(row.get("user_nickname")) or None,
        text=_sv(row.get("text")),
        parent_id=None,
        engagement=engagement,
        metadata={"video_id": video_id} if video_id else {},
    )


def _map_facebook_row(row: dict) -> RawSocialPost:
    """Mapea una fila de facebook_comments al esquema Bronze.

    Columnas esperadas:
        titulo_post, descripcion_post, comentario, comentario_clean,
        comentario_norm, likes, url, fecha, archivo_origen,
        candidatos_detectados, capa_deteccion
    """
    import hashlib

    comentario = _sv(row.get("comentario"))
    fecha = _sv(row.get("fecha"))
    content_hash = hashlib.md5(f"{comentario}{fecha}".encode("utf-8")).hexdigest()[:16]
    fb_id = f"fb_{content_hash}"

    likes = _iv(row.get("likes"))
    return RawSocialPost(
        id=fb_id,
        source="facebook",
        source_id=content_hash,
        datetime_utc=_sv(fecha) or None,
        username=None,
        text=comentario,
        parent_id=None,
        engagement={"likes": likes} if likes is not None else {},
        metadata={
            k: _sv(row.get(field))
            for k, field in {
                "post_title": "titulo_post",
                "post_url": "url",
                "source_file": "archivo_origen",
                "candidates_detected": "candidatos_detectados",
                "detection_layer": "capa_deteccion",
            }.items()
            if _sv(row.get(field))
        },
    )


def _map_external_row(row: dict) -> RawSocialPost:
    """Mapea una fila de CSV genérico externo al esquema Bronze."""
    import uuid
    # Usar un id proporcionado o generar uno
    raw_id = str(row.get("id", uuid.uuid4().hex[:12]))
    ext_id = raw_id if raw_id.startswith("ext_") else f"ext_{raw_id}"

    # Buscar campos posibles para el texto
    text = row.get("text", row.get("content", row.get("mensaje", row.get("body", ""))))
    
    # Buscar fecha
    dt = row.get("date", row.get("datetime", row.get("fecha", None)))
    
    # Buscar autor
    user = row.get("username", row.get("author", row.get("usuario", None)))

    return RawSocialPost(
        id=ext_id,
        source="other",
        source_id=raw_id.replace("ext_", "", 1),
        datetime_utc=dt,
        username=user,
        text=str(text),
        parent_id=None,
        engagement={},
        metadata={"import_source": "external_csv"}
    )


def _map_fb_parlamentarias_row(row: dict) -> RawSocialPost:
    """Mapea una fila del CSV de parlamentarias (formato Facebook apify).

    Columnas: postTitle, postDescription, text, likesCount, facebookUrl
    Sin columna de fecha — el ID se genera por hash del texto + url.
    Filas donde text es una URL (filas de post vacías) se descartan.
    """
    import hashlib

    text = _sv(row.get("text"))
    # Filtrar filas que no son comentarios (text contiene una URL del post)
    if text.startswith("http://") or text.startswith("https://"):
        raise ValueError("fila de post sin comentario — se omite")

    url = _sv(row.get("facebookUrl"))
    content_hash = hashlib.md5(f"{text}{url}".encode("utf-8")).hexdigest()[:16]

    likes = _iv(row.get("likesCount"))
    return RawSocialPost(
        id=f"fb_{content_hash}",
        source="facebook",
        source_id=content_hash,
        datetime_utc=None,
        username=None,
        text=text,
        parent_id=None,
        engagement={"likes": likes} if likes is not None else {},
        metadata={
            k: v
            for k, v in {
                "post_title": _sv(row.get("postTitle")),
                "post_description": _sv(row.get("postDescription")),
                "post_url": url,
            }.items()
            if v
        },
    )


# ── Lector especializado para CSVs con doble-quoting (formato apify) ──────

def _fix_double_encoding(text: str) -> str:
    """
    Corrige texto doblemente codificado: UTF-8 leído como Latin-1 y re-guardado.
    Ejemplo: 'prÃ³ximo' → 'próximo'
    """
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _read_double_quoted_csv(path: Path) -> pd.DataFrame:
    """
    Lee CSVs con doble-quoting generados por apify/Excel.

    Formato: cada línea es una fila CSV de 2 columnas donde la columna 1
    contiene el CSV interno completo entre comillas. Los campos internos
    también usan comillas dobles. El texto puede tener doble-encoding UTF-8.

    Estrategia: two-pass parsing — primero extraer la columna 1 con
    csv.reader (resuelve el wrapper externo), luego parsear el contenido
    interno como CSV independiente.
    """
    COLS = ["postTitle", "postDescription", "text", "likesCount", "facebookUrl"]
    BOM_JUNK = "ï»¿\xef\xbb\xbf﻿"
    rows = []

    with open(path, "rb") as f:
        raw_bytes = f.read()

    content = raw_bytes.decode("utf-8", errors="replace")

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        # Paso 1: parsear la línea como CSV de 2 columnas para extraer el wrapper externo
        try:
            outer = next(csv.reader([line], quotechar='"', doublequote=True))
        except (StopIteration, csv.Error):
            continue

        inner_text = outer[0].lstrip(BOM_JUNK) if outer else ""
        if not inner_text:
            continue

        # Paso 2: parsear el contenido interno como CSV
        try:
            fields = next(csv.reader([inner_text], quotechar='"', doublequote=True))
        except (StopIteration, csv.Error):
            continue

        if not any(fields):
            continue

        # Ignorar filas de encabezado
        if any("postTitle" in f or "facebookUrl" in f for f in fields):
            continue

        # Rellenar hasta 5 columnas y corregir doble-encoding en cada campo
        while len(fields) < len(COLS):
            fields.append("")
        fields = [_fix_double_encoding(f) for f in fields[:len(COLS)]]
        rows.append(dict(zip(COLS, fields)))

    return pd.DataFrame(rows, columns=COLS)


# ── Mapeo central ──────────────────────────────────────────────────

_MAPPERS = {
    "twitter":          _map_twitter_row,
    "youtube":          _map_youtube_row,
    "tiktok":           _map_tiktok_row,
    "facebook":         _map_facebook_row,
    "fb_parlamentarias": _map_fb_parlamentarias_row,
    "external":         _map_external_row,
}

# Fuentes que requieren un lector CSV especializado en lugar de pd.read_csv estándar
_SPECIAL_READERS: dict[str, callable] = {
    "fb_parlamentarias": _read_double_quoted_csv,
}


def ingest_csv(csv_path: str, source: str) -> list[RawSocialPost]:
    """
    Lee un CSV de scraper o datos genéricos y lo convierte a una lista de RawSocialPost.

    Args:
        csv_path: Ruta al archivo CSV.
        source: Nombre de la fuente ("twitter", "youtube", "external").

    Returns:
        Lista de RawSocialPost validados.
    """
    path = Path(csv_path)
    if not path.exists():
        log.warning("CSV no encontrado: %s — se omite.", path)
        return []

    mapper = _MAPPERS.get(source)
    if mapper is None:
        log.error("No hay mapeador para la fuente '%s'. Fuentes disponibles: %s",
                  source, list(_MAPPERS.keys()))
        return []

    special_reader = _SPECIAL_READERS.get(source)
    try:
        if special_reader:
            df = special_reader(path)
        else:
            df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        log.warning("CSV vacio (sin columnas): %s — se omite.", path.name)
        return []
    except pd.errors.ParserError as exc:
        log.error("CSV mal formado: %s (%s) — se omite.", path.name, exc)
        return []

    if len(df) == 0:
        log.warning("CSV sin filas: %s — se omite.", path.name)
        return []

    log.info("Leyendo %d filas de %s (%s)", len(df), path.name, source)

    posts: list[RawSocialPost] = []
    errors = 0
    for _, row in df.iterrows():
        try:
            post = mapper(row.to_dict())
            posts.append(post)
        except Exception as e:
            errors += 1
            if errors <= 5:
                log.warning("Error mapeando fila (source=%s): %s", source, e)

    if errors > 5:
        log.warning("... y %d errores más suprimidos.", errors - 5)

    log.info("Mapeados %d/%d registros exitosamente de %s", len(posts), len(df), source)
    return posts


def run_ingestion(
    twitter_csv: str | None = None,
    youtube_csv: str | None = None,
    tiktok_csv: str | None = None,
    facebook_csv: str | None = None,
    external_csv: str | None = None,
) -> list[RawSocialPost]:
    """
    Ejecuta la ingestión de todos los CSVs disponibles.

    Args:
        twitter_csv:  Ruta al CSV de Twitter.
        youtube_csv:  Ruta al CSV de YouTube.
        tiktok_csv:   Ruta al CSV de TikTok (comments).
        facebook_csv: Ruta al CSV de Facebook (comments).
        external_csv: Ruta al CSV genérico externo.

    Returns:
        Lista combinada de RawSocialPost de todas las fuentes.
    """
    all_posts: list[RawSocialPost] = []

    sources = {
        "twitter":  twitter_csv,
        "youtube":  youtube_csv,
        "tiktok":   tiktok_csv,
        "facebook": facebook_csv,
        "external": external_csv,
    }

    for source_name, csv_path in sources.items():
        if csv_path:
            posts = ingest_csv(csv_path, source_name)
            all_posts.extend(posts)

    log.info("Total de registros ingeridos: %d", len(all_posts))
    return all_posts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquestador de ingestión: lee CSVs de scrapers y los normaliza a Bronze.",
    )
    parser.add_argument(
        "--twitter-csv",
        default=None,
        help="Ruta al CSV generado por el scraper de Twitter.",
    )
    parser.add_argument(
        "--youtube-csv",
        default=None,
        help="Ruta al CSV generado por el scraper de YouTube.",
    )
    parser.add_argument(
        "--external-csv",
        default=None,
        help="Ruta a un CSV genérico externo con datos adicionales.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_PROJECT_ROOT / "data" / "bronze"),
        help="Directorio de salida para los archivos Bronze.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    posts = run_ingestion(
        twitter_csv=args.twitter_csv,
        youtube_csv=args.youtube_csv,
        external_csv=args.external_csv,
    )

    if not posts:
        log.warning("No se ingirieron registros. Verifica las rutas a los CSVs.")
        return

    # Importar el store de Bronze para almacenar
    from data_pipeline.bronze.store import store_bronze_posts
    store_bronze_posts(posts, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
