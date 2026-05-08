"""
validator.py — Validación de datos Silver con contratos Pydantic.

Toma dicts parciales (post-cleaner + post-anonymizer) y los valida
contra el esquema CleanPost. Los registros inválidos se separan
para inspección manual.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.silver import CleanPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("silver.validator")


def validate_silver(records: list[dict]) -> tuple[list[CleanPost], list[dict]]:
    """
    Valida registros contra el esquema CleanPost.

    Returns:
        (valid_posts, invalid_records) — los válidos como CleanPost,
        los inválidos como dicts con el error adjunto.
    """
    valid: list[CleanPost] = []
    invalid: list[dict] = []

    for record in records:
        try:
            post = CleanPost(**record)
            valid.append(post)
        except ValidationError as e:
            record["_validation_error"] = str(e)
            invalid.append(record)

    if invalid:
        log.warning("Validación Silver: %d/%d registros inválidos", len(invalid), len(records))
        for inv in invalid[:3]:
            log.debug("  Error: %s", inv.get("_validation_error", "?")[:200])

    log.info("Validación Silver: %d válidos, %d inválidos", len(valid), len(invalid))
    return valid, invalid
