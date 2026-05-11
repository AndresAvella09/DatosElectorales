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


# ── Mapeadores por fuente ──────────────────────────────────────────


def _map_twitter_row(row: dict) -> RawSocialPost:
    """Mapea una fila de CSV de Twitter al esquema Bronze."""
    tweet_id = str(row.get("id", "")).replace(".0", "")
    return RawSocialPost(
        id=f"tw_{tweet_id}",
        source="twitter",
        source_id=tweet_id,
        datetime_utc=row.get("datetime"),
        username=row.get("username"),
        text=row.get("content", ""),
        parent_id=None,
        engagement={
            k: row.get(k)
            for k in ("replies", "retweets", "likes")
            if row.get(k) is not None and str(row.get(k)) != "nan"
        },
        metadata={
            "query": row.get("Query", row.get("query", "")),
        },
    )


def _map_youtube_row(row: dict) -> RawSocialPost:
    """Mapea una fila de CSV de YouTube al esquema Bronze."""
    raw_id = str(row.get("id", ""))
    # YouTube ya genera IDs con prefijo "yt_", pero verificamos
    yt_id = raw_id if raw_id.startswith("yt_") else f"yt_{raw_id}"
    source_id = raw_id.replace("yt_", "", 1)

    parent_raw = row.get("parent_id", "")
    parent_id = str(parent_raw) if parent_raw and str(parent_raw) != "nan" else None

    return RawSocialPost(
        id=yt_id,
        source="youtube",
        source_id=source_id,
        datetime_utc=row.get("date"),
        username=row.get("username"),
        text=row.get("text", ""),
        parent_id=parent_id,
        engagement={
            k: row.get(k)
            for k in ("likes", "views")
            if row.get(k) is not None and str(row.get(k)) != "nan"
        },
        metadata={
            k: row.get(k)
            for k in ("video_id", "video_title", "query")
            if row.get(k) is not None and str(row.get(k)) != "nan"
        },
    )


def _map_tiktok_row(row: dict) -> RawSocialPost:
    """Mapea una fila de tiktok_comments al esquema Bronze.

    Esperado del scraper packages/scrapers/tiktok/scrape_tiktok.py:
        video_id, comment_id, create_time, user_unique_id, user_nickname,
        text, digg_count, reply_count
    """
    raw_id = str(row.get("comment_id", ""))
    if not raw_id or raw_id == "nan":
        raise ValueError("tiktok row sin comment_id")
    tk_id = raw_id if raw_id.startswith("tk_") else f"tk_{raw_id}"

    def _safe_int(v):
        if v is None or str(v) in ("", "nan"):
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    return RawSocialPost(
        id=tk_id,
        source="tiktok",
        source_id=raw_id,
        datetime_utc=row.get("create_time"),
        username=row.get("user_unique_id") or row.get("user_nickname"),
        text=row.get("text", ""),
        parent_id=None,
        engagement={
            k: _safe_int(row.get(src))
            for k, src in (("likes", "digg_count"), ("replies", "reply_count"))
            if _safe_int(row.get(src)) is not None
        },
        metadata={
            "video_id": row.get("video_id"),
            "user_nickname": row.get("user_nickname"),
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


# ── Mapeo central ──────────────────────────────────────────────────

_MAPPERS = {
    "twitter": _map_twitter_row,
    "youtube": _map_youtube_row,
    "tiktok":  _map_tiktok_row,
    "external": _map_external_row,
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

    df = pd.read_csv(path)
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
    external_csv: str | None = None,
) -> list[RawSocialPost]:
    """
    Ejecuta la ingestión de todos los CSVs disponibles (Twitter, YouTube, External).

    Args:
        twitter_csv: Ruta al CSV de Twitter.
        youtube_csv: Ruta al CSV de YouTube.
        external_csv: Ruta al CSV genérico externo.

    Returns:
        Lista combinada de RawSocialPost de todas las fuentes.
    """
    all_posts: list[RawSocialPost] = []

    sources = {
        "twitter": twitter_csv,
        "youtube": youtube_csv,
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
