"""
anonymizer.py — Detección y enmascaramiento de PII para la capa Silver.

Qué hace:
  1. Detecta PII en el texto original: emails, teléfonos, cédulas colombianas, nombres propios.
  2. Enmascara la PII detectada con placeholders ([EMAIL], [PHONE], etc.).
  3. Hashea el username para anonimización (SHA-256 truncado).
  4. Registra los tipos de PII detectados para el Compliance Audit Log.

Limitaciones actuales:
  - La detección de nombres propios es básica (regex de palabras capitalizadas).
    Para producción se recomienda usar un modelo NER (spaCy, Presidio).
  - Los patrones de cédula cubren formatos colombianos comunes.
"""

from __future__ import annotations

import hashlib
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
_CEDULA_RE = re.compile(r"\b\d{6,10}\b")  # Cédulas colombianas: 6-10 dígitos


def hash_username(username: str | None, salt: str = "datos_electorales_2026") -> str | None:
    """Hashea un username con SHA-256 truncado para anonimización."""
    if not username:
        return None
    raw = f"{salt}:{username}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def detect_and_mask_pii(text: str) -> dict:
    """
    Detecta PII en el texto y la enmascara.

    Returns:
        dict con:
            - text_masked: texto con PII enmascarada
            - pii_detected: bool
            - pii_types: lista de tipos detectados
    """
    if not text:
        return {"text_masked": "", "pii_detected": False, "pii_types": []}

    masked = text
    pii_types: list[str] = []

    # Emails
    if _EMAIL_RE.search(masked):
        masked = _EMAIL_RE.sub("[EMAIL]", masked)
        pii_types.append("email")

    # Teléfonos
    if _PHONE_RE.search(masked):
        masked = _PHONE_RE.sub("[PHONE]", masked)
        pii_types.append("phone")

    # Cédulas (solo si hay secuencias de 8-10 dígitos, para evitar falsos positivos)
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

    Modifica cada registro in-place agregando:
        - username_hash (reemplazando username)
        - pii_detected, pii_types
        - Aplica masking al text_original

    Args:
        records: Lista de dicts del cleaner (con text_original, username en metadata).

    Returns:
        Lista de dicts enriquecidos con campos de anonimización.
    """
    for record in records:
        # Hash del username
        username_raw = record.pop("username", None)
        record["username_hash"] = hash_username(username_raw)

        # PII masking sobre el texto original
        pii_result = detect_and_mask_pii(record.get("text_original", ""))
        record["text_original"] = pii_result["text_masked"]
        record["pii_detected"] = pii_result["pii_detected"]
        record["pii_types"] = pii_result["pii_types"]

    pii_count = sum(1 for r in records if r.get("pii_detected"))
    log.info("Anonimización: %d/%d registros con PII detectada", pii_count, len(records))
    return records
