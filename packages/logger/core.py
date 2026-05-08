"""
core.py — Configuración centralizada de logging.

Proporciona un logger configurado con formato consistente para todos
los módulos del monorepo. Soporta output a consola y opcionalmente a archivo.

Uso:
    from logger import get_logger
    log = get_logger("data_pipeline.silver")
    log.info("Procesando %d registros", count)

El formato de salida es:
    2026-05-08 12:00:00 [INFO] data_pipeline.silver — Procesando 150 registros
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED: set[str] = set()


def get_logger(
    name: str,
    level: str | None = None,
    log_file: str | None = None,
) -> logging.Logger:
    """
    Obtiene un logger configurado con formato consistente.

    Args:
        name: Nombre del logger (ej. "data_pipeline.silver", "scraper.twitter").
        level: Nivel de log. Si no se especifica, usa la variable de entorno
               LOG_LEVEL o INFO por defecto.
        log_file: Ruta opcional a un archivo de log.

    Returns:
        Logger configurado.
    """
    logger = logging.getLogger(name)

    # Evitar configurar el mismo logger más de una vez
    if name in _CONFIGURED:
        return logger

    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logger.setLevel(resolved_level)

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATE_FORMAT)

    # Handler de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler de archivo (opcional)
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Evitar propagación al logger root para no duplicar mensajes
    logger.propagate = False

    _CONFIGURED.add(name)
    return logger
