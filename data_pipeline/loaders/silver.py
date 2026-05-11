"""
silver.py — Promueve un run de raw.posts a silver.posts.

Etapa 2 del pipeline (§7.3 del plan):
  1. SELECT raw.posts WHERE run_id = $1.
  2. Reconstruir RawSocialPost desde raw_payload + columnas.
  3. cleaner.clean_posts() + anonymizer.anonymize_records() + validator.
  4. langdetect (con fallback al heuristico del cleaner).
  5. UPSERT a silver.posts con cleaned_at fijo para todo el run.

Nota sobre la PK de silver.posts:
  silver.posts es una tabla particionada con PK (id, cleaned_at). Cada
  llamada a promote_run usa un cleaned_at unico (now() al inicio), asi
  que el UPSERT con on_conflict=(id, cleaned_at) deduplica dentro del
  run pero deja historico al reprocessar.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts import CleanPost, RawSocialPost  # noqa: E402
from logger import get_logger  # noqa: E402

from data_pipeline.loaders._client import get_client  # noqa: E402
from data_pipeline.silver.anonymizer import anonymize_records  # noqa: E402
from data_pipeline.silver.cleaner import clean_posts, detect_language  # noqa: E402
from data_pipeline.silver.validator import validate_silver  # noqa: E402

log = get_logger("loaders.silver")

UPSERT_BATCH = 200
SELECT_PAGE = 1000


def _detect_lang_strict(text: str, fallback: str | None) -> str | None:
    """Intenta langdetect, cae al heuristico del cleaner si falla."""
    if not text or len(text.strip()) < 3:
        return None
    try:
        from langdetect import DetectorFactory, LangDetectException, detect

        DetectorFactory.seed = 0  # determinismo
        return detect(text)
    except (ImportError, LangDetectException, Exception):  # noqa: BLE001
        return fallback


def _fetch_raw_for_run(run_id: str) -> list[RawSocialPost]:
    """Lee todas las filas de raw.posts asociadas a este run."""
    sb = get_client()
    posts: list[RawSocialPost] = []
    offset = 0
    while True:
        res = (
            sb.schema("raw")
            .table("posts")
            .select("id, source, source_id, raw_payload")
            .eq("run_id", run_id)
            .range(offset, offset + SELECT_PAGE - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        for row in rows:
            payload = row.get("raw_payload") or {}
            try:
                posts.append(
                    RawSocialPost(
                        id=row["id"],
                        source=row["source"],
                        source_id=row["source_id"],
                        datetime_utc=payload.get("datetime_utc"),
                        username=payload.get("username"),
                        text=payload.get("text", ""),
                        parent_id=payload.get("parent_id"),
                        engagement=payload.get("engagement") or {},
                        metadata=payload.get("metadata") or {},
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Saltando raw.posts.id=%s: %s", row.get("id"), exc)
        if len(rows) < SELECT_PAGE:
            break
        offset += SELECT_PAGE

    log.info("raw.posts leidos para run=%s: %d filas", run_id[:8], len(posts))
    return posts


def _existing_silver_ids(ids: list[str]) -> set[str]:
    """IDs ya presentes en silver.posts (para marcar duplicados sin re-pegar)."""
    if not ids:
        return set()
    sb = get_client()
    existing: set[str] = set()
    # in_() puede ser pesado con miles de ids — chunkeamos.
    CHUNK = 200
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i : i + CHUNK]
        res = (
            sb.schema("silver")
            .table("posts")
            .select("id")
            .in_("id", chunk)
            .execute()
        )
        for row in res.data or []:
            existing.add(row["id"])
    return existing


def _clean_post_to_row(
    post: CleanPost,
    *,
    run_id: str,
    cleaned_at: str,
) -> dict[str, Any]:
    return {
        "id": post.id,
        "source": post.source,
        "source_id": post.source_id,
        "datetime_utc": post.datetime_utc,
        "username_hash": post.username_hash,
        "text_clean": post.text_clean,
        "text_original": post.text_original,
        "parent_id": post.parent_id,
        "engagement": post.engagement,
        "metadata": post.metadata,
        "lang": post.lang,
        "pii_detected": post.pii_detected,
        "pii_types": post.pii_types,
        "is_duplicate": post.is_duplicate,
        "cleaned_at": cleaned_at,
        "run_id": run_id,
    }


def _upsert_in_batches(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sb = get_client()
    total = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = rows[i : i + UPSERT_BATCH]
        (
            sb.schema("silver")
            .table("posts")
            .upsert(chunk, on_conflict="id,cleaned_at")
            .execute()
        )
        total += len(chunk)
        log.debug("silver.posts upsert: %d/%d", total, len(rows))
    return total


# ── API publica ───────────────────────────────────────────────────


def promote_run(run_id: str) -> int:
    """
    Lee raw.posts(run_id), aplica cleaner+anonymizer, escribe silver.posts.

    Politica de dedup: si un id ya existe en silver, no se vuelve a escribir
    (la fila vieja queda intacta). Solo se UPSERTean ids realmente nuevos.
    Esto evita duplicar filas con cleaned_at distinto en cada rerun y
    mantiene silver compacto.

    Returns:
        Numero de filas escritas en silver.posts (solo nuevas).
    """
    cleaned_at = datetime.now(timezone.utc).isoformat()
    raw_posts = _fetch_raw_for_run(run_id)
    if not raw_posts:
        log.warning("No hay filas raw para run=%s", run_id[:8])
        return 0

    # IDs que ya existen en silver — el cleaner los descarta directamente
    # via deduplicate(existing_ids=...), no entran al pipeline.
    existing = _existing_silver_ids([p.id for p in raw_posts])
    n_skipped = len(existing)
    if n_skipped:
        log.info(
            "silver.posts ya contiene %d/%d ids del run — se skippean",
            n_skipped, len(raw_posts),
        )

    # Pipeline de limpieza (cleaner descarta los que ya estan en silver).
    partial = clean_posts(raw_posts, existing_ids=existing)
    if not partial:
        log.info("Silver: 0 filas nuevas para run=%s (todas duplicadas)",
                 run_id[:8])
        return 0
    partial = anonymize_records(partial)

    valid, invalid = validate_silver(partial)
    if invalid:
        log.warning("Silver: %d filas invalidas descartadas", len(invalid))

    # Refinar lang con langdetect cuando es posible
    for post in valid:
        if post.lang in (None, "unknown"):
            post.lang = _detect_lang_strict(post.text_original, post.lang)

    rows = [_clean_post_to_row(p, run_id=run_id, cleaned_at=cleaned_at) for p in valid]
    written = _upsert_in_batches(rows)
    log.info("silver.posts: %d filas UPSERTeadas (run=%s)", written, run_id[:8])
    return written
