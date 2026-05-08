"""
Silver Layer — Esquema de datos limpios (CleanPost).

Este esquema representa un post DESPUÉS de pasar por:
    1. Deduplicación (eliminación de duplicados por id)
    2. Normalización de texto (lowercase, limpieza de URLs, menciones)
    3. Anonimización (PII masking: nombres, emails, teléfonos enmascarados)
    4. Validación de esquema

Campos adicionales respecto a Bronze:
    - text_clean: Texto normalizado y limpio (sin URLs, sin menciones, lowercase)
    - text_original: Texto original antes de la limpieza (para auditoría)
    - pii_detected: Indica si se detectó PII en el texto original
    - pii_types: Lista de tipos de PII detectados (email, phone, name, etc.)
    - is_duplicate: Si el post fue marcado como duplicado
    - lang: Idioma detectado del texto

Ejemplo de uso:
    >>> from contracts.silver import CleanPost
    >>> post = CleanPost(
    ...     id="tw_1234567890",
    ...     source="twitter",
    ...     source_id="1234567890",
    ...     text_original="@usuario Colombia merece un cambio real!",
    ...     text_clean="colombia merece un cambio real",
    ...     lang="es",
    ... )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class CleanPost(BaseModel):
    """Esquema para un post limpio y anonimizado (capa Silver)."""

    id: str = Field(..., description="ID único prefijado por fuente.")
    source: str = Field(..., description="Red social de origen.")
    source_id: str = Field(..., description="ID original del post en la plataforma.")
    datetime_utc: str | None = Field(default=None, description="Fecha ISO 8601 UTC.")
    username_hash: str | None = Field(
        default=None,
        description="Hash del username original (anonimizado, para agrupar sin revelar identidad).",
    )
    text_original: str = Field(default="", description="Texto original antes de limpieza.")
    text_clean: str = Field(
        default="",
        description="Texto normalizado: sin URLs, sin menciones, lowercase.",
    )
    parent_id: str | None = Field(default=None, description="ID del post padre.")
    engagement: dict[str, Any] = Field(
        default_factory=dict,
        description="Métricas de engagement.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Datos adicionales de la fuente.",
    )
    lang: str | None = Field(
        default=None,
        description="Idioma detectado del texto (ISO 639-1, ej. 'es', 'en').",
    )
    pii_detected: bool = Field(
        default=False,
        description="True si se detectó PII en el texto original.",
    )
    pii_types: list[str] = Field(
        default_factory=list,
        description="Tipos de PII detectados: 'email', 'phone', 'name', 'cedula', etc.",
    )
    is_duplicate: bool = Field(
        default=False,
        description="True si el post fue marcado como duplicado.",
    )
    cleaned_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp de cuándo se procesó en Silver.",
    )
