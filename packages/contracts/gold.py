"""
Gold Layer — Esquema enriquecido con features para ML (EnrichedPost).

Este esquema representa un post DESPUÉS de pasar por Feature Engineering:
    1. Features NLP (longitud, conteo de palabras, presencia de hashtags/emojis)
    2. Features temporales (hora del día, día de la semana, días hasta elección)
    3. Features de engagement (ratios, scores)
    4. Resultado del modelo de sentimiento (cuando esté disponible)

Campos adicionales respecto a Silver:
    - Sección NLP: word_count, char_count, has_hashtags, has_emojis, has_urls_original
    - Sección Temporal: hour_of_day, day_of_week, days_until_election
    - Sección Engagement: engagement_score
    - Sección ML: sentiment_label, sentiment_score (null hasta que ML los llene)

Ejemplo de uso:
    >>> from contracts.gold import EnrichedPost
    >>> post = EnrichedPost(
    ...     id="tw_1234567890",
    ...     source="twitter",
    ...     text_clean="colombia merece un cambio real",
    ...     word_count=6,
    ...     sentiment_label=None,  # Pendiente del modelo
    ... )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class EnrichedPost(BaseModel):
    """Esquema enriquecido con features listo para ML (capa Gold)."""

    # ── Identificadores ──
    id: str = Field(..., description="ID único prefijado por fuente.")
    source: str = Field(..., description="Red social de origen.")
    source_id: str = Field(default="", description="ID original en la plataforma.")
    datetime_utc: str | None = Field(default=None, description="Fecha ISO 8601 UTC.")

    # ── Texto ──
    text_clean: str = Field(default="", description="Texto normalizado de Silver.")

    # ── Features NLP ──
    word_count: int = Field(default=0, description="Número de palabras en text_clean.")
    char_count: int = Field(default=0, description="Número de caracteres en text_clean.")
    has_hashtags: bool = Field(default=False, description="Si el texto original contenía hashtags.")
    has_emojis: bool = Field(default=False, description="Si el texto original contenía emojis.")
    has_urls_original: bool = Field(
        default=False,
        description="Si el texto original contenía URLs.",
    )

    # ── Features Temporales ──
    hour_of_day: int | None = Field(default=None, description="Hora del día UTC (0-23).")
    day_of_week: int | None = Field(
        default=None,
        description="Día de la semana (0=lunes, 6=domingo).",
    )
    days_until_election: int | None = Field(
        default=None,
        description="Días restantes hasta la elección (negativo si ya pasó).",
    )

    # ── Features de Engagement ──
    engagement: dict[str, Any] = Field(
        default_factory=dict,
        description="Métricas de engagement originales.",
    )
    engagement_score: float | None = Field(
        default=None,
        description="Score agregado de engagement (calculado en feature_builder).",
    )

    # ── Resultados ML (llenados por el equipo de ML) ──
    sentiment_label: str | None = Field(
        default=None,
        description="Etiqueta de sentimiento: 'positive', 'negative', 'neutral'. Null hasta ML.",
    )
    sentiment_score: float | None = Field(
        default=None,
        description="Score de confianza del modelo de sentimiento [0, 1]. Null hasta ML.",
    )
    candidate_mentioned: str | None = Field(
        default=None,
        description="Candidato mencionado detectado (si aplica).",
    )

    # ── Metadata ──
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Datos adicionales.",
    )
    enriched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp de cuándo se enriqueció en Gold.",
    )
