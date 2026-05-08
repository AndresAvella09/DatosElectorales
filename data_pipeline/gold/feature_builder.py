"""
feature_builder.py — Construcción de features para la capa Gold.

Qué hace:
  1. Features NLP: word_count, char_count (extraídos de text_clean).
  2. Features Temporales: hour_of_day, day_of_week, days_until_election.
  3. Engagement Score: score agregado ponderado de las métricas.
  4. Empaqueta todo en el esquema EnrichedPost (Gold).

Nota: sentiment_label y sentiment_score se dejan en None.
      El equipo de ML los llenará usando ml/interfaces/sentiment_wrapper.py.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.gold import EnrichedPost  # noqa: E402
from contracts.silver import CleanPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("gold.feature_builder")

# Fecha de las elecciones presidenciales de Colombia 2026 (primer turno estimado)
ELECTION_DATE = datetime(2026, 5, 31, tzinfo=timezone.utc)


def _compute_temporal_features(datetime_str: str | None) -> dict:
    """Extrae features temporales de un datetime ISO string."""
    if not datetime_str:
        return {"hour_of_day": None, "day_of_week": None, "days_until_election": None}

    try:
        # Manejar varios formatos de fecha
        dt_str = datetime_str.replace("Z", "+00:00")
        if " " in dt_str and "T" not in dt_str:
            dt_str = dt_str.replace(" ", "T")
        if "+" not in dt_str and "-" not in dt_str[10:]:
            dt_str += "+00:00"
        dt = datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return {"hour_of_day": None, "day_of_week": None, "days_until_election": None}

    return {
        "hour_of_day": dt.hour,
        "day_of_week": dt.weekday(),  # 0=lunes, 6=domingo
        "days_until_election": (ELECTION_DATE - dt).days,
    }


def _compute_engagement_score(engagement: dict) -> float | None:
    """
    Calcula un score de engagement ponderado.

    Pesos:
        likes=1, retweets/shares=2, replies/comments=3, views=0.01

    El score se normaliza logarítmicamente para evitar que posts virales
    dominen completamente.
    """
    import math

    weights = {"likes": 1, "retweets": 2, "shares": 2, "replies": 3, "comments": 3, "views": 0.01}
    total = 0.0
    has_data = False

    for metric, weight in weights.items():
        value = engagement.get(metric)
        if value is not None:
            try:
                total += float(value) * weight
                has_data = True
            except (ValueError, TypeError):
                pass

    if not has_data:
        return None

    # Log scale para normalizar
    return round(math.log1p(total), 4)


def build_features(posts: list[CleanPost]) -> list[EnrichedPost]:
    """
    Construye features Gold a partir de posts Silver.

    Returns:
        Lista de EnrichedPost con features NLP, temporales y engagement.
        Los campos de ML (sentiment_label, sentiment_score) quedan en None.
    """
    enriched: list[EnrichedPost] = []

    for post in posts:
        temporal = _compute_temporal_features(post.datetime_utc)
        engagement_score = _compute_engagement_score(post.engagement)

        ep = EnrichedPost(
            id=post.id,
            source=post.source,
            source_id=post.source_id,
            datetime_utc=post.datetime_utc,
            text_clean=post.text_clean,
            # NLP features
            word_count=len(post.text_clean.split()) if post.text_clean else 0,
            char_count=len(post.text_clean) if post.text_clean else 0,
            has_hashtags=False,  # Info perdida en Silver, se puede agregar si se pasa
            has_emojis=False,
            has_urls_original=False,
            # Temporal features
            hour_of_day=temporal["hour_of_day"],
            day_of_week=temporal["day_of_week"],
            days_until_election=temporal["days_until_election"],
            # Engagement
            engagement=post.engagement,
            engagement_score=engagement_score,
            # ML — pendiente del equipo de modelos
            sentiment_label=None,
            sentiment_score=None,
            candidate_mentioned=None,
            # Metadata
            metadata=post.metadata,
        )
        enriched.append(ep)

    log.info("Feature engineering: %d registros enriquecidos → Gold", len(enriched))
    return enriched
