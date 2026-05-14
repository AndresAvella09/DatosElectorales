"""
gold.py — Promueve un run de silver.posts a gold.features.

Etapa 4 del pipeline (§7.5 del plan):
  1. SELECT silver.posts WHERE run_id = $1 AND is_duplicate = false.
  2. Reconstruir CleanPost.
  3. feature_builder.build_features() -> EnrichedPost.
  4. UPSERT a gold.features (on conflict id).

sentiment_label, sentiment_score y candidate_mentioned quedan en NULL;
los rellena el equipo de ML asincronamente.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts import CleanPost, EnrichedPost  # noqa: E402
from logger import get_logger  # noqa: E402

from data_pipeline.gold.feature_builder import build_features  # noqa: E402
from data_pipeline.loaders._client import get_client  # noqa: E402

log = get_logger("loaders.gold")

UPSERT_BATCH = 200
SELECT_PAGE = 1000


def _fetch_silver_for_run(run_id: str) -> list[CleanPost]:
    """Lee silver.posts(run_id) excluyendo duplicados."""
    sb = get_client()
    posts: list[CleanPost] = []
    offset = 0
    while True:
        res = (
            sb.schema("silver")
            .table("posts")
            .select(
                "id, source, source_id, datetime_utc, author_id, "
                "text_clean, text_original, parent_id, engagement, metadata, "
                "lang, pii_detected, pii_types, is_duplicate, cleaned_at"
            )
            .eq("run_id", run_id)
            .eq("is_duplicate", False)
            .range(offset, offset + SELECT_PAGE - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        for row in rows:
            try:
                posts.append(CleanPost(**row))
            except Exception as exc:  # noqa: BLE001
                log.warning("Saltando silver.posts.id=%s: %s", row.get("id"), exc)
        if len(rows) < SELECT_PAGE:
            break
        offset += SELECT_PAGE

    log.info("silver.posts leidos para run=%s: %d filas", run_id[:8], len(posts))
    return posts


def _enriched_to_row(post: EnrichedPost, run_id: str) -> dict[str, Any]:
    return {
        "id": post.id,
        "source": post.source,
        "datetime_utc": post.datetime_utc,
        "word_count": post.word_count,
        "char_count": post.char_count,
        "has_hashtags": post.has_hashtags,
        "has_emojis": post.has_emojis,
        "has_urls_original": post.has_urls_original,
        "hour_of_day": post.hour_of_day,
        "day_of_week": post.day_of_week,
        "days_until_election": post.days_until_election,
        "engagement": post.engagement,
        "engagement_score": post.engagement_score,
        "sentiment_label": post.sentiment_label,
        "sentiment_score": post.sentiment_score,
        "candidate_mentioned": post.candidate_mentioned,
        "run_id": run_id,
    }


def _upsert_in_batches(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sb = get_client()
    total = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = rows[i : i + UPSERT_BATCH]
        sb.schema("gold").table("features").upsert(chunk, on_conflict="id").execute()
        total += len(chunk)
        log.debug("gold.features upsert: %d/%d", total, len(rows))
    return total


def refresh_views() -> None:
    """
    REFRESH MATERIALIZED VIEW CONCURRENTLY public.v_sentiment_daily.

    Nota: supabase-py no expone REFRESH directamente; lo hacemos via una
    funcion SQL que el A1 deberia exponer como RPC. Por ahora lo logueamos
    como TODO; A5/A10 lo invocan por psql o RPC cuando este disponible.
    """
    log.info("[TODO] REFRESH MATERIALIZED VIEW public.v_sentiment_daily — pendiente de RPC")


# ── API publica ───────────────────────────────────────────────────


def promote_run(run_id: str, refresh: bool = False) -> int:
    """
    Lee silver.posts(run_id), construye features, escribe gold.features.

    Args:
        run_id:  UUID compartido por todo el run.
        refresh: Si True, intenta refrescar las matviews al final
                 (no-op por ahora; ver refresh_views()).

    Returns:
        Numero de filas escritas en gold.features.
    """
    silver_posts = _fetch_silver_for_run(run_id)
    if not silver_posts:
        log.warning("No hay filas silver para run=%s", run_id[:8])
        return 0

    enriched = build_features(silver_posts)
    rows = [_enriched_to_row(p, run_id=run_id) for p in enriched]
    written = _upsert_in_batches(rows)
    log.info("gold.features: %d filas UPSERTeadas (run=%s)", written, run_id[:8])

    if refresh:
        refresh_views()

    return written
