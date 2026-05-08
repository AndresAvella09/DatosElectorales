"""
Bronze Layer — Esquema de datos crudos (Raw Social Post).

Este esquema define la estructura estandarizada para TODOS los posts
que ingresan al sistema desde cualquier scraper. Cada scraper produce
datos con columnas distintas; el orchestrator se encarga de mapear
las columnas de cada fuente a este esquema unificado.

Campos:
    - id: Identificador único del post (prefijado por fuente, ej. "tw_123", "yt_abc")
    - source: Red social de origen ("twitter", "youtube", "facebook", "tiktok")
    - source_id: ID original del post en la plataforma
    - datetime_utc: Fecha y hora en UTC (ISO 8601)
    - username: Nombre de usuario del autor
    - text: Contenido textual del post/comentario
    - parent_id: ID del post padre (para respuestas/replies, vacío si es top-level)
    - engagement: Métricas de engagement como dict flexible (likes, replies, retweets, views, etc.)
    - metadata: Datos adicionales específicos de la fuente (query, video_title, etc.)
    - ingested_at: Timestamp de cuándo se ingirió el dato al pipeline

Ejemplo de uso:
    >>> from contracts.bronze import RawSocialPost
    >>> post = RawSocialPost(
    ...     id="tw_1234567890",
    ...     source="twitter",
    ...     source_id="1234567890",
    ...     datetime_utc="2026-05-08T12:00:00Z",
    ...     username="usuario_ejemplo",
    ...     text="Colombia merece un cambio real en 2026",
    ...     engagement={"likes": 42, "retweets": 10, "replies": 3},
    ...     metadata={"query": "elecciones Colombia 2026"},
    ... )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RawSocialPost(BaseModel):
    """Esquema unificado para un post crudo de redes sociales (capa Bronze)."""

    id: str = Field(
        ...,
        description="ID único prefijado por fuente, ej. 'tw_123', 'yt_abc'.",
    )
    source: str = Field(
        ...,
        description="Red social de origen: 'twitter', 'youtube', 'facebook', 'tiktok'.",
    )
    source_id: str = Field(
        ...,
        description="ID original del post en la plataforma.",
    )
    datetime_utc: str | None = Field(
        default=None,
        description="Fecha y hora en formato ISO 8601 UTC.",
    )
    username: str | None = Field(
        default=None,
        description="Nombre de usuario del autor.",
    )
    text: str = Field(
        default="",
        description="Contenido textual del post o comentario.",
    )
    parent_id: str | None = Field(
        default=None,
        description="ID del post padre (para replies). None si es top-level.",
    )
    engagement: dict[str, Any] = Field(
        default_factory=dict,
        description="Métricas de engagement: likes, retweets, replies, views, etc.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Datos adicionales específicos de la fuente (query, video_title, etc.).",
    )
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp ISO 8601 de cuándo se ingirió al pipeline.",
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed = {"twitter", "youtube", "facebook", "tiktok", "other"}
        if v.lower() not in allowed:
            raise ValueError(f"source debe ser una de {allowed}, recibido: '{v}'")
        return v.lower()

    @field_validator("text")
    @classmethod
    def clean_text(cls, v: str) -> str:
        return (v or "").strip()
