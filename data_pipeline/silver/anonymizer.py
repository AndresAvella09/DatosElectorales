"""
anonymizer.py — Detección y enmascaramiento de PII para la capa Silver.

Qué hace:
  1. Detecta PII en el texto original: emails, teléfonos, cédulas colombianas.
  2. Enmascara la PII detectada con placeholders ([EMAIL], [PHONE], [CEDULA]).
  3. Extrae author_id desde el campo username (ya viene pseudoanónimo en los CSV fuente).
  4. Limpia metadata: elimina campos de identidad (user_nickname, author_nickname).
  5. Registra los tipos de PII detectados para el Compliance Audit Log.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

log = get_logger("silver.anonymizer")

# ── Patrones PII ───────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+57\s?)?(?:\(?\d{1,3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}")
_CEDULA_RE = re.compile(r"\b\d{6,10}\b")

# Campos de identidad que nunca deben llegar a Silver en metadata
_IDENTITY_METADATA_KEYS = {"user_nickname", "author_nickname", "username", "channel_name"}


def detect_and_mask_pii(text: str) -> dict:
    """
    Detecta PII en el texto y la enmascara.

    Returns:
        dict con text_masked, pii_detected, pii_types.
    """
    if not text:
        return {"text_masked": "", "pii_detected": False, "pii_types": []}

    masked = text
    pii_types: list[str] = []

    if _EMAIL_RE.search(masked):
        masked = _EMAIL_RE.sub("[EMAIL]", masked)
        pii_types.append("email")

    if _PHONE_RE.search(masked):
        masked = _PHONE_RE.sub("[PHONE]", masked)
        pii_types.append("phone")

    cedula_matches = _CEDULA_RE.findall(masked)
    real_cedulas = [m for m in cedula_matches if 8 <= len(m) <= 10]
    if real_cedulas:
        for ced in real_cedulas:
            masked = masked.replace(ced, "[CEDULA]")
        pii_types.append("cedula")

    return {
        "text_masked": masked,
        "pii_detected": len(pii_types) > 0,
        "pii_types": pii_types,
    }


def anonymize_records(records: list[dict]) -> list[dict]:
    """
    Aplica anonimización a una lista de registros parciales de CleanPost.

    Por cada registro:
      - Extrae `username` → `author_id` (ya es pseudoanónimo en los CSV fuente).
      - Filtra campos de identidad de `metadata`.
      - Aplica PII masking al text_original.

    Args:
        records: Lista de dicts del cleaner (incluyen campo `username`).

    Returns:
        Lista de dicts listos para construir CleanPost.
    """
    for record in records:
        # author_id: el username ya viene pseudoanónimo desde el CSV fuente
        # (twitter_user_xxx, yt_user_xxx, user_unique_id de TikTok, None en Facebook)
        username_raw = record.pop("username", None)
        record["author_id"] = username_raw if username_raw else None

        # Limpiar metadata: quitar cualquier campo de identidad
        if "metadata" in record:
            record["metadata"] = {
                k: v for k, v in record["metadata"].items()
                if k not in _IDENTITY_METADATA_KEYS
            }

        # PII masking sobre el texto original
        pii_result = detect_and_mask_pii(record.get("text_original", ""))
        record["text_original"] = pii_result["text_masked"]
        record["pii_detected"] = pii_result["pii_detected"]
        record["pii_types"] = pii_result["pii_types"]

    pii_count = sum(1 for r in records if r.get("pii_detected"))
    log.info("Anonimización: %d/%d registros con PII detectada", pii_count, len(records))
    return records
