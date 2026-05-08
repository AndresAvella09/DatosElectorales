"""
store.py — Almacenamiento de datos Bronze particionados por fuente y fecha.

QUÉ HACE ESTE SCRIPT                                              
Recibe una lista de RawSocialPost (ya validados por el            
orchestrator) y los almacena en disco con la siguiente estructura:
                                                                  
data/bronze/                                                      
  ├── twitter/                                                    
  │   ├── 2026-05-08.jsonl                                        
  │   └── 2026-05-09.jsonl                                        
  ├── youtube/                                                    
  │   └── 2026-05-08.jsonl                                        
  └── ...                                                         
                                                                  
Formato: JSON Lines (.jsonl) — una línea por registro.            
Particionado: por source (carpeta) y fecha de ingestión (archivo).
Modo: append — si el archivo ya existe, agrega al final.          

Uso desde código:
    from data-pipeline.bronze.store import store_bronze_posts
    store_bronze_posts(posts, output_dir="data/bronze")
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.bronze import RawSocialPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("bronze.store")


def store_bronze_posts(
    posts: list[RawSocialPost],
    output_dir: str | Path = "data/bronze",
) -> dict[str, int]:
    """
    Almacena una lista de RawSocialPost en archivos JSONL particionados.

    Particionado:
        - Por fuente (source): cada fuente tiene su propia carpeta.
        - Por fecha de ingestión: cada día tiene su propio archivo .jsonl.

    Args:
        posts: Lista de RawSocialPost validados.
        output_dir: Directorio raíz de Bronze (default: data/bronze).

    Returns:
        Dict con el conteo de registros almacenados por fuente.
        Ej: {"twitter": 150, "youtube": 230}
    """
    output_path = Path(output_dir)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Agrupar posts por fuente
    by_source: dict[str, list[RawSocialPost]] = defaultdict(list)
    for post in posts:
        by_source[post.source].append(post)

    counts: dict[str, int] = {}

    for source, source_posts in by_source.items():
        source_dir = output_path / source
        source_dir.mkdir(parents=True, exist_ok=True)

        file_path = source_dir / f"{today}.jsonl"
        mode = "a"  # Append para no sobreescribir datos previos del mismo día

        with open(file_path, mode, encoding="utf-8") as f:
            for post in source_posts:
                line = post.model_dump_json()
                f.write(line + "\n")

        counts[source] = len(source_posts)
        log.info(
            "Bronze: almacenados %d registros en %s",
            len(source_posts),
            file_path,
        )

    log.info("Bronze store completado: %s", counts)
    return counts


def load_bronze_posts(
    source: str,
    date: str | None = None,
    bronze_dir: str | Path = "data/bronze",
) -> list[RawSocialPost]:
    """
    Carga posts de Bronze desde disco.

    Args:
        source: Fuente a cargar ("twitter", "youtube", etc.).
        date: Fecha específica (YYYY-MM-DD). Si es None, carga todos los archivos.
        bronze_dir: Directorio raíz de Bronze.

    Returns:
        Lista de RawSocialPost.
    """
    bronze_path = Path(bronze_dir) / source

    if not bronze_path.exists():
        log.warning("Directorio Bronze no encontrado: %s", bronze_path)
        return []

    if date:
        files = [bronze_path / f"{date}.jsonl"]
    else:
        files = sorted(bronze_path.glob("*.jsonl"))

    posts: list[RawSocialPost] = []
    for file_path in files:
        if not file_path.exists():
            continue
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    posts.append(RawSocialPost(**data))

    log.info("Bronze: cargados %d registros de %s (date=%s)", len(posts), source, date or "all")
    return posts
