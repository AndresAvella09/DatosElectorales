"""
media.py — Carga directa de datos de medios de comunicación a schema media.

Tablas destino:
  media.mentions        — menciones en artículos (mentions.csv)
  media.share_of_voice  — SoV + momentum (share_of_voice.csv + momentum.csv fusionados)
  media.vote_intentions — intenciones de voto (vote_intentions_clean.csv)

No pasa por el pipeline bronze/silver/gold. Los CSVs ya están limpios.
UPSERT idempotente por PK de cada tabla.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from logger import get_logger  # noqa: E402

from data_pipeline.loaders._client import get_client  # noqa: E402

log = get_logger("loaders.media")

UPSERT_BATCH = 300


# ── Utilidades ─────────────────────────────────────────────────────

def _sanitize(obj: Any) -> Any:
    """Reemplaza float NaN/Inf con None para JSON compliance."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _read(path: str | Path, required_cols: list[str]) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV no encontrado: {p}")
    df = pd.read_csv(p, encoding="utf-8-sig")
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"{p.name}: columnas faltantes {missing}. Encontradas: {df.columns.tolist()}")
    log.info("Leídas %d filas de %s", len(df), p.name)
    return df


def _upsert(table: str, rows: list[dict], on_conflict: str) -> int:
    if not rows:
        return 0
    sb = get_client()
    total = 0
    for i in range(0, len(rows), UPSERT_BATCH):
        chunk = [_sanitize(r) for r in rows[i: i + UPSERT_BATCH]]
        sb.schema("media").table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
        log.debug("media.%s upsert: %d/%d", table, total, len(rows))
    log.info("media.%s: %d filas UPSERTeadas", table, total)
    return total


# ── Loaders por tabla ──────────────────────────────────────────────

def load_mentions(csv_path: str | Path) -> int:
    df = _read(csv_path, ["article_id", "medio", "fecha", "candidato"])

    rows = []
    for _, r in df.iterrows():
        row: dict[str, Any] = {
            "article_id":  str(r.get("article_id", "")).strip(),
            "url":         str(r["url"]) if pd.notna(r.get("url")) else None,
            "medio":       str(r["medio"]).strip(),
            "fecha":       str(r["fecha"])[:10],
            "titulo":      str(r["titulo"]) if pd.notna(r.get("titulo")) else None,
            "candidato":   str(r["candidato"]).strip(),
            "menciones":   int(r["menciones"]) if pd.notna(r.get("menciones")) else 1,
            "titulo_flag": bool(int(r["titulo_flag"])) if pd.notna(r.get("titulo_flag")) else False,
            "evento_tipo": str(r["evento_tipo"]) if pd.notna(r.get("evento_tipo")) else None,
            "region":      str(r["region"]) if pd.notna(r.get("region")) else None,
        }
        if not row["article_id"] or not row["candidato"]:
            continue
        rows.append(row)

    return _upsert("mentions", rows, "article_id,candidato")


def load_share_of_voice(
    sov_path: str | Path,
    momentum_path: str | Path | None = None,
) -> int:
    """
    Carga share_of_voice.csv y opcionalmente fusiona momentum.csv.

    momentum.csv tiene la misma PK (fecha, medio, candidato) y agrega
    rolling_7 y momentum. El UPSERT fusiona ambos datasets en una tabla.
    """
    df_sov = _read(sov_path, ["fecha", "medio", "candidato"])

    # Índice base desde SoV
    records: dict[tuple, dict] = {}
    for _, r in df_sov.iterrows():
        key = (str(r["fecha"])[:10], str(r["medio"]).strip(), str(r["candidato"]).strip())
        records[key] = {
            "fecha":          key[0],
            "medio":          key[1],
            "candidato":      key[2],
            "menciones":      int(r["menciones"]) if pd.notna(r.get("menciones")) else None,
            "share_of_voice": float(r["share_of_voice"]) if pd.notna(r.get("share_of_voice")) else None,
            "rolling_7":      None,
            "momentum":       None,
        }

    # Fusionar momentum si se provee
    if momentum_path:
        df_mom = _read(momentum_path, ["fecha", "medio", "candidato"])
        for _, r in df_mom.iterrows():
            key = (str(r["fecha"])[:10], str(r["medio"]).strip(), str(r["candidato"]).strip())
            base = records.get(key, {
                "fecha": key[0], "medio": key[1], "candidato": key[2],
                "menciones": int(r["menciones"]) if pd.notna(r.get("menciones")) else None,
                "share_of_voice": float(r["share_of_voice"]) if pd.notna(r.get("share_of_voice")) else None,
            })
            base["rolling_7"] = float(r["rolling_7"]) if pd.notna(r.get("rolling_7")) else None
            base["momentum"]  = float(r["momentum"])  if pd.notna(r.get("momentum"))  else None
            records[key] = base

    return _upsert("share_of_voice", list(records.values()), "fecha,medio,candidato")


def load_vote_intentions(csv_path: str | Path) -> int:
    df = _read(csv_path, ["article_id", "medio", "fecha", "candidato"])

    rows = []
    for _, r in df.iterrows():
        row: dict[str, Any] = {
            "article_id":    str(r.get("article_id", "")).strip(),
            "url":           str(r["url"]) if pd.notna(r.get("url")) else None,
            "medio":         str(r["medio"]).strip(),
            "fecha":         str(r["fecha"])[:10],
            "titulo":        str(r["titulo"]) if pd.notna(r.get("titulo")) else None,
            "candidato":     str(r["candidato"]).strip(),
            "candidato_raw": str(r["candidato_raw"]) if pd.notna(r.get("candidato_raw")) else None,
            "porcentaje":    float(r["porcentaje"]) if pd.notna(r.get("porcentaje")) else None,
            "encuestadora":  str(r["encuestadora"]) if pd.notna(r.get("encuestadora")) else None,
            "contexto":      str(r["contexto"]) if pd.notna(r.get("contexto")) else None,
        }
        if not row["article_id"] or not row["candidato"]:
            continue
        rows.append(row)

    return _upsert("vote_intentions", rows, "article_id,candidato")


# ── API pública ────────────────────────────────────────────────────

def load_momentum(csv_path: str | Path) -> int:
    df = _read(csv_path, ["fecha", "medio", "candidato"])

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "fecha":          str(r["fecha"])[:10],
            "medio":          str(r["medio"]).strip(),
            "candidato":      str(r["candidato"]).strip(),
            "menciones":      int(r["menciones"]) if pd.notna(r.get("menciones")) else None,
            "share_of_voice": float(r["share_of_voice"]) if pd.notna(r.get("share_of_voice")) else None,
            "rolling_7":      float(r["rolling_7"]) if pd.notna(r.get("rolling_7")) else None,
            "momentum":       float(r["momentum"]) if pd.notna(r.get("momentum")) else None,
        })

    return _upsert("momentum", rows, "fecha,medio,candidato")


def load_all(
    mentions_csv: str | Path | None = None,
    sov_csv: str | Path | None = None,
    momentum_csv: str | Path | None = None,
    vote_csv: str | Path | None = None,
) -> dict[str, int]:
    """
    Carga todos los datasets de medios disponibles.

    Returns:
        Dict con conteo de filas insertadas por tabla.
    """
    results: dict[str, int] = {}

    if mentions_csv:
        results["mentions"] = load_mentions(mentions_csv)

    if sov_csv:
        results["share_of_voice"] = load_share_of_voice(sov_csv, momentum_csv)

    if momentum_csv:
        results["momentum"] = load_momentum(momentum_csv)

    if vote_csv:
        results["vote_intentions"] = load_vote_intentions(vote_csv)

    total = sum(results.values())
    log.info("media: carga completa — %d filas en %d tablas", total, len(results))
    return results
