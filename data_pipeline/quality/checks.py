"""
checks.py — Data Quality Gate: validaciones de completeness, freshness y anomalías.

Qué hace:
  1. Completeness: verifica que campos obligatorios no estén vacíos.
  2. Freshness: verifica que los datos no sean más antiguos que un umbral.
  3. Volume Anomaly: detecta si el volumen de datos es anormalmente bajo/alto.
  4. Genera un reporte de calidad (dict) con PASS/FAIL por cada check.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.silver import CleanPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("quality.checks")


def check_completeness(
    posts: list[CleanPost],
    required_fields: list[str] | None = None,
) -> dict:
    """Verifica que campos obligatorios no estén vacíos."""
    if required_fields is None:
        required_fields = ["id", "source", "text_clean"]

    total = len(posts)
    if total == 0:
        return {"check": "completeness", "status": "FAIL", "reason": "No hay registros"}

    issues: dict[str, int] = {}
    for field in required_fields:
        empty_count = sum(1 for p in posts if not getattr(p, field, None))
        if empty_count > 0:
            issues[field] = empty_count

    pct_complete = ((total - sum(issues.values())) / (total * len(required_fields))) * 100

    return {
        "check": "completeness",
        "status": "PASS" if not issues else "WARN" if pct_complete > 90 else "FAIL",
        "total_records": total,
        "issues": issues,
        "completeness_pct": round(pct_complete, 2),
    }


def check_freshness(
    posts: list[CleanPost],
    max_age_days: int = 30,
) -> dict:
    """Verifica que los datos no sean más antiguos que max_age_days."""
    if not posts:
        return {"check": "freshness", "status": "FAIL", "reason": "No hay registros"}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    stale = 0

    for post in posts:
        if post.datetime_utc:
            try:
                dt = datetime.fromisoformat(post.datetime_utc.replace("Z", "+00:00"))
                if dt < cutoff:
                    stale += 1
            except (ValueError, TypeError):
                pass

    return {
        "check": "freshness",
        "status": "PASS" if stale == 0 else "WARN" if stale < len(posts) * 0.1 else "FAIL",
        "stale_records": stale,
        "total_records": len(posts),
        "max_age_days": max_age_days,
    }


def check_volume(
    current_count: int,
    expected_min: int = 10,
    expected_max: int = 100_000,
) -> dict:
    """Detecta anomalías de volumen (demasiados o muy pocos registros)."""
    if current_count < expected_min:
        status = "FAIL"
        reason = f"Volumen demasiado bajo: {current_count} < {expected_min}"
    elif current_count > expected_max:
        status = "WARN"
        reason = f"Volumen inusualmente alto: {current_count} > {expected_max}"
    else:
        status = "PASS"
        reason = None

    result = {"check": "volume", "status": status, "count": current_count}
    if reason:
        result["reason"] = reason
    return result


def run_quality_gate(posts: list[CleanPost]) -> dict:
    """Ejecuta todos los checks y retorna un reporte consolidado."""
    completeness = check_completeness(posts)
    freshness = check_freshness(posts)
    volume = check_volume(len(posts))

    checks = [completeness, freshness, volume]
    overall = "PASS" if all(c["status"] == "PASS" for c in checks) else \
              "WARN" if all(c["status"] != "FAIL" for c in checks) else "FAIL"

    report = {
        "overall_status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_records": len(posts),
        "checks": checks,
    }

    log.info("Quality Gate: %s (%d registros)", overall, len(posts))
    for c in checks:
        log.info("  %s: %s", c["check"], c["status"])

    return report
