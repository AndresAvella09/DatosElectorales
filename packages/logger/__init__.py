"""
logger — Logger centralizado para el monorepo DatosElectorales.

Uso:
    from logger import get_logger
    log = get_logger("mi_modulo")
    log.info("Mensaje")
"""

from logger.core import get_logger

__all__ = ["get_logger"]
