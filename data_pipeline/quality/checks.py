"""
checks.py — Quality Gate bloqueante (§7.4 y §8 del plan).

Cinco checks sobre el subset de silver.posts perteneciente a un run:

  1. completeness — campos obligatorios (id, source, text_clean, datetime_utc)
                    no vacios en mas del 95% de los registros.
  2. freshness    — ningun registro con datetime_utc futuro; >=80% con
                    fecha < 30 dias.
  3. volume       — el count del run no varia mas de +-70% vs promedio de
                    los ultimos 7 runs success (con fallback a min absoluto
                    si no hay historico suficiente).
  4. schema       — 100% de los registros validan contra CleanPost.
  5. pii_leak     — 0 registros con pii_detected=True cuyo text_original
                    todavia exponga PII raw (email/phone/cedula) sin
                    enmascarar; 0 metadata con claves de PII conocidas.

Cada check devuelve un dict con:
    {"check": "<name>", "status": "PASS|WARN|FAIL", **detalles}

run_quality_gate(posts, *, prior_volumes=None) consolida los 5 checks y
devuelve un reporte:
    {
      "overall": "PASS|WARN|FAIL",
      "checks": [<dict>, ...],
      "total_records": <int>,
      "timestamp": <iso>,
    }

Politica de promocion (§8.2):
  - PASS: continuar.
  - WARN: continuar + alertar.
  - FAIL: abortar, marcar run como quality_failed, no escribir Gold.
"""

from __future__ import annotations

import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.silver import CleanPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("quality.checks")


# ── Thresholds (centralizados) ─────────────────────────────────────

COMPLETENESS_REQUIRED_FIELDS = ("id", "source", "text_clean", "datetime_utc")
COMPLETENESS_PASS_PCT = 95.0
COMPLETENESS_WARN_PCT = 90.0

FRESHNESS_MAX_AGE_DAYS = 30
FRESHNESS_STALE_PASS_PCT = 20.0  # <=20% stale es PASS
FRESHNESS_STALE_WARN_PCT = 50.0  # 20-50% stale es WARN; >50% es FAIL

VOLUME_TOLERANCE_PCT = 70.0   # +-70% vs promedio 7 runs
VOLUME_MIN_ABSOLUTE = 10      # fallback cuando no hay historico

PII_LEAK_KEYS_IN_METADATA = {
    "username", "user_name", "user_nickname", "nickname",
    "user_unique_id", "user_id", "author", "author_name",
    "screen_name", "handle", "display_name", "usuario",
}

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+57\s?)?(?:\(?\d{1,3}\)?[\s.-]?)?\d{3}[\s.-]?\d{4}")
_CEDULA_RE = re.compile(r"\b\d{8,10}\b")


# ── Helpers ────────────────────────────────────────────────────────


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = value.replace("Z", "+00:00") if isinstance(value, str) else str(value)
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _field_value(post: CleanPost, field: str):
    return getattr(post, field, None)


def _is_empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


# ── Checks ─────────────────────────────────────────────────────────


def check_completeness(
    posts: list[CleanPost],
    required_fields: Iterable[str] = COMPLETENESS_REQUIRED_FIELDS,
) -> dict:
    """% de registros con TODOS los campos obligatorios presentes."""
    total = len(posts)
    if total == 0:
        return {"check": "completeness", "status": "FAIL",
                "reason": "no_records", "completeness_pct": 0.0}

    fields = list(required_fields)
    empty_counts: dict[str, int] = {f: 0 for f in fields}
    fully_complete = 0
    for p in posts:
        all_present = True
        for f in fields:
            if _is_empty(_field_value(p, f)):
                empty_counts[f] += 1
                all_present = False
        if all_present:
            fully_complete += 1

    pct = (fully_complete / total) * 100
    if pct >= COMPLETENESS_PASS_PCT:
        status = "PASS"
    elif pct >= COMPLETENESS_WARN_PCT:
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "check": "completeness",
        "status": status,
        "total_records": total,
        "fully_complete": fully_complete,
        "completeness_pct": round(pct, 2),
        "empty_by_field": {f: c for f, c in empty_counts.items() if c},
    }


def check_freshness(
    posts: list[CleanPost],
    max_age_days: int = FRESHNESS_MAX_AGE_DAYS,
) -> dict:
    """No fechas futuras; mayoria reciente."""
    total = len(posts)
    if total == 0:
        return {"check": "freshness", "status": "FAIL", "reason": "no_records"}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    stale = 0
    future = 0
    unparseable = 0

    for p in posts:
        dt = _parse_dt(p.datetime_utc)
        if dt is None:
            unparseable += 1
            continue
        if dt > now:
            future += 1
        elif dt < cutoff:
            stale += 1

    stale_pct = (stale / total) * 100
    if future > 0:
        status = "FAIL"
        reason = f"{future}_future_dates"
    elif stale_pct > FRESHNESS_STALE_WARN_PCT:
        status = "FAIL"
        reason = f"stale_pct={stale_pct:.1f}>{FRESHNESS_STALE_WARN_PCT}"
    elif stale_pct > FRESHNESS_STALE_PASS_PCT:
        status = "WARN"
        reason = f"stale_pct={stale_pct:.1f}>{FRESHNESS_STALE_PASS_PCT}"
    else:
        status = "PASS"
        reason = None

    out = {
        "check": "freshness",
        "status": status,
        "total_records": total,
        "stale_records": stale,
        "future_records": future,
        "unparseable_dates": unparseable,
        "stale_pct": round(stale_pct, 2),
        "max_age_days": max_age_days,
    }
    if reason:
        out["reason"] = reason
    return out


def check_volume(
    current_count: int,
    prior_volumes: list[int] | None = None,
    *,
    tolerance_pct: float = VOLUME_TOLERANCE_PCT,
    min_absolute: int = VOLUME_MIN_ABSOLUTE,
) -> dict:
    """
    Variacion vs promedio de runs previos.

    - Sin historico: solo aplica min_absolute (FAIL si current < min, else PASS).
    - Con >=2 runs previos: PASS si current esta dentro de +-tolerance_pct
      del promedio; WARN si esta entre +-tolerance y +-(tolerance*2);
      FAIL si esta por fuera.
    """
    if current_count < min_absolute:
        return {
            "check": "volume", "status": "FAIL",
            "count": current_count, "min_absolute": min_absolute,
            "reason": f"below_min_absolute({min_absolute})",
        }

    prior = [v for v in (prior_volumes or []) if v is not None and v > 0]
    if len(prior) < 2:
        return {
            "check": "volume", "status": "PASS",
            "count": current_count,
            "baseline": None,
            "note": "no_baseline_yet (necesitan >=2 runs previos)",
        }

    avg = statistics.mean(prior)
    deviation_pct = abs(current_count - avg) / avg * 100
    if deviation_pct <= tolerance_pct:
        status = "PASS"
    elif deviation_pct <= tolerance_pct * 2:
        status = "WARN"
    else:
        status = "FAIL"

    return {
        "check": "volume", "status": status,
        "count": current_count,
        "baseline_avg": round(avg, 2),
        "baseline_runs": len(prior),
        "deviation_pct": round(deviation_pct, 2),
        "tolerance_pct": tolerance_pct,
    }


def check_schema(posts: list[CleanPost]) -> dict:
    """
    Re-valida cada registro contra el contrato CleanPost.

    Los registros que llegan aca ya son instancias de CleanPost, pero
    podrian tener campos rellenados con valores invalidos (ej. lang con
    caracteres no permitidos, source fuera del whitelist, etc.). Hacemos
    un model_validate(dump) para que pydantic re-evalue los validators.
    """
    total = len(posts)
    if total == 0:
        return {"check": "schema", "status": "FAIL", "reason": "no_records"}

    invalid = 0
    sample_errors: list[str] = []
    for p in posts:
        try:
            CleanPost.model_validate(p.model_dump())
        except Exception as exc:  # noqa: BLE001
            invalid += 1
            if len(sample_errors) < 3:
                sample_errors.append(f"{p.id}: {exc}")

    invalid_pct = (invalid / total) * 100
    status = "PASS" if invalid == 0 else "FAIL"
    out = {
        "check": "schema", "status": status,
        "total_records": total,
        "invalid": invalid,
        "invalid_pct": round(invalid_pct, 2),
    }
    if sample_errors:
        out["sample_errors"] = sample_errors
    return out


def check_pii_leak(posts: list[CleanPost]) -> dict:
    """
    Verifica que la anonimizacion realmente removio la PII:

    - Para cada post con pii_detected=True, text_original NO debe tener
      matches raw de email/phone/cedula (deberian estar como placeholders).
    - metadata no debe contener claves conocidas de PII (username,
      user_nickname, author, etc.).
    """
    total = len(posts)
    if total == 0:
        return {"check": "pii_leak", "status": "FAIL", "reason": "no_records"}

    leaked_text = 0
    leaked_meta = 0
    sample: list[str] = []

    for p in posts:
        text = p.text_original or ""
        if p.pii_detected:
            if (_EMAIL_RE.search(text)
                    or _PHONE_RE.search(text)
                    or _CEDULA_RE.search(text)):
                leaked_text += 1
                if len(sample) < 3:
                    sample.append(f"text_leak:{p.id}")

        meta = p.metadata or {}
        if isinstance(meta, dict):
            bad_keys = [
                k for k in meta.keys()
                if str(k).lower() in PII_LEAK_KEYS_IN_METADATA
            ]
            if bad_keys:
                leaked_meta += 1
                if len(sample) < 3:
                    sample.append(f"meta_leak:{p.id}:{bad_keys}")

    leaked = leaked_text + leaked_meta
    out = {
        "check": "pii_leak",
        "status": "PASS" if leaked == 0 else "FAIL",
        "total_records": total,
        "leaked_text": leaked_text,
        "leaked_metadata": leaked_meta,
    }
    if sample:
        out["sample_violations"] = sample
    return out


# ── Orquestacion ───────────────────────────────────────────────────


def run_quality_gate(
    posts: list[CleanPost],
    *,
    prior_volumes: list[int] | None = None,
) -> dict:
    """
    Ejecuta los 5 checks y devuelve el reporte consolidado.

    overall = FAIL si cualquier check es FAIL.
    overall = WARN si nadie es FAIL pero alguien es WARN.
    overall = PASS si todos PASS.
    """
    checks = [
        check_completeness(posts),
        check_freshness(posts),
        check_volume(len(posts), prior_volumes=prior_volumes),
        check_schema(posts),
        check_pii_leak(posts),
    ]

    statuses = [c["status"] for c in checks]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "PASS"

    report = {
        "overall": overall,
        "total_records": len(posts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }

    log.info("Quality Gate: %s (%d registros)", overall, len(posts))
    for c in checks:
        log.info("  - %-12s %s", c["check"], c["status"])
    return report
