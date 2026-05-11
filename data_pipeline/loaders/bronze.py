"""
bronze.py — Ingesta CSV crudo -> Storage + raw.posts.

Etapa 1 del pipeline (§7.2 del plan):
  1. Calcular sha256 del archivo.
  2. Subir el CSV a bucket bronze-raw como <source>/<YYYY-MM-DD>/<filename>.
  3. Parsear CSV con orchestrator.ingest_csv() -> list[RawSocialPost].
  4. UPSERT a raw.posts (on conflict id).
  5. Mover archivo de data/inbox/ a data/processed/<YYYY-MM-DD>/.

Idempotencia:
  - Si el sha256 ya existe en raw.posts.source_sha256, no se reingiere.
  - El UPSERT por id evita duplicados a nivel registro.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts import RawSocialPost  # noqa: E402
from logger import get_logger  # noqa: E402

from data_pipeline.ingestion.orchestrator import ingest_csv  # noqa: E402
from data_pipeline.loaders._client import get_client  # noqa: E402

log = get_logger("loaders.bronze")

BRONZE_BUCKET = "bronze-raw"
DEFAULT_INBOX = _PROJECT_ROOT / "data" / "inbox"
DEFAULT_PROCESSED = _PROJECT_ROOT / "data" / "processed"
UPSERT_BATCH = 200


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _already_ingested(source_sha256: str) -> bool:
    """True si algun raw.posts existente tiene este sha256."""
    sb = get_client()
    res = (
        sb.schema("raw")
        .table("posts")
        .select("id")
        .eq("source_sha256", source_sha256)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def _upload_to_storage(path: Path, source: str) -> str:
    """Sube el archivo al bucket y devuelve la storage_path remota."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    remote = f"{source}/{today}/{path.name}"

    sb = get_client()
    with open(path, "rb") as f:
        body = f.read()

    # upsert=true para que reintentos no fallen con "already exists".
    try:
        sb.storage.from_(BRONZE_BUCKET).upload(
            path=remote,
            file=body,
            file_options={"content-type": "text/csv", "upsert": "true"},
        )
    except Exception as exc:
        # Algunas versiones de supabase-py reportan 409 como excepcion
        # incluso con upsert=true. Lo loggeamos y seguimos.
        log.warning("Upload a Storage devolvio aviso (path=%s): %s", remote, exc)

    log.info("Storage: %s subido como %s/%s", path.name, BRONZE_BUCKET, remote)
    return f"{BRONZE_BUCKET}/{remote}"


def _post_to_raw_row(
    post: RawSocialPost,
    *,
    run_id: str,
    storage_path: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Convierte un RawSocialPost al row que entra a raw.posts."""
    return {
        "id": post.id,
        "source": post.source,
        "source_id": post.source_id,
        "storage_path": storage_path,
        "ingested_at": post.ingested_at,
        "run_id": run_id,
        "raw_payload": {
            "datetime_utc": post.datetime_utc,
            "username": post.username,
            "text": post.text,
            "parent_id": post.parent_id,
            "engagement": post.engagement,
            "metadata": post.metadata,
        },
        "source_sha256": source_sha256,
    }


def _dedupe_by_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Colapsa filas con el mismo `id` (gana la ultima). PostgREST rechaza
    UPSERTs con PK duplicada en un mismo batch ("ON CONFLICT DO UPDATE
    command cannot affect row a second time"), y los CSV crudos a veces
    traen el mismo comment_id repetido.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_id[r["id"]] = r
    return list(by_id.values())


def _upsert_in_batches(rows: list[dict[str, Any]]) -> int:
    """UPSERT chunkeado para no exceder limites de PostgREST."""
    if not rows:
        return 0
    deduped = _dedupe_by_id(rows)
    dropped = len(rows) - len(deduped)
    if dropped:
        log.warning("raw.posts: %d filas con id duplicado colapsadas", dropped)
    sb = get_client()
    total = 0
    for i in range(0, len(deduped), UPSERT_BATCH):
        chunk = deduped[i : i + UPSERT_BATCH]
        sb.schema("raw").table("posts").upsert(chunk, on_conflict="id").execute()
        total += len(chunk)
        log.debug("raw.posts upsert: %d/%d", total, len(deduped))
    return total


def _archive(csv_path: Path, processed_dir: Path = DEFAULT_PROCESSED) -> Path:
    """Mueve el CSV de inbox/ a processed/<YYYY-MM-DD>/<filename>."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest_dir = processed_dir / today
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / csv_path.name
    # Si ya existe, sufijar con timestamp para no perder data.
    if dest.exists():
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        dest = dest_dir / f"{csv_path.stem}.{stamp}{csv_path.suffix}"
    shutil.move(str(csv_path), str(dest))
    log.info("Archivado: %s -> %s", csv_path.name, dest)
    return dest


# ── API publica ───────────────────────────────────────────────────


def load_csv(
    csv_path: str | Path,
    source: str,
    run_id: str,
    *,
    skip_storage: bool = True,
    archive: bool = True,
) -> int:
    """
    Carga un CSV a Bronze (raw.posts + opcionalmente Storage).

    Args:
        csv_path:     Ruta local al CSV.
        source:       'twitter' | 'youtube' | 'external' | 'tiktok'.
        run_id:       UUID del run (creado con runs.start()).
        skip_storage: Default True para ahorrar espacio del bucket en plan
                      free. Pasar False explicitamente si se quiere conservar
                      el CSV crudo en Storage para auditoria.
        archive:      Si True, mueve el CSV a data/processed/ tras exito.

    Returns:
        Numero de filas UPSERTeadas en raw.posts.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV no existe: {path}")

    # Skip rapido por archivo vacio antes de calcular sha o subir nada.
    if path.stat().st_size == 0:
        log.warning("Archivo vacio: %s — se archiva sin procesar.", path.name)
        if archive:
            _archive(path)
        return 0

    sha = _sha256(path)
    log.info("Procesando %s (sha256=%s, run=%s)", path.name, sha[:12], run_id[:8])

    if _already_ingested(sha):
        log.warning(
            "Archivo %s ya fue ingerido previamente (sha256 match). Saltando.",
            path.name,
        )
        if archive:
            _archive(path)
        return 0

    # Parsear ANTES de subir a Storage: si el CSV no tiene posts validos,
    # no gastamos espacio del bucket subiendolo.
    posts = ingest_csv(str(path), source)
    if not posts:
        log.warning("Orchestrator no produjo posts a partir de %s", path.name)
        if archive:
            _archive(path)
        return 0

    storage_path = (
        _upload_to_storage(path, source)
        if not skip_storage
        else f"local://processed/{path.name}"
    )

    rows = [
        _post_to_raw_row(p, run_id=run_id, storage_path=storage_path, source_sha256=sha)
        for p in posts
    ]
    inserted = _upsert_in_batches(rows)
    log.info("raw.posts: %d filas UPSERTeadas (run=%s)", inserted, run_id[:8])

    if archive:
        _archive(path)

    return inserted


def scan_inbox(
    inbox_dir: str | Path = DEFAULT_INBOX,
) -> list[tuple[Path, str]]:
    """
    Escanea data/inbox/<source>/<date>/*.csv y devuelve [(path, source), ...].

    El orden no esta garantizado; el watcher (A3) usa esto como fallback.
    """
    base = Path(inbox_dir)
    if not base.exists():
        return []
    out: list[tuple[Path, str]] = []
    for source_dir in base.iterdir():
        if not source_dir.is_dir():
            continue
        source = source_dir.name
        for csv in source_dir.rglob("*.csv"):
            out.append((csv, source))
    return out
