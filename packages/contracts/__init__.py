"""
contracts — Esquemas Pydantic para el pipeline Medallion.

Importar desde aquí:
    from contracts.bronze import RawSocialPost
    from contracts.silver import CleanPost
    from contracts.gold import EnrichedPost
"""

from contracts.bronze import RawSocialPost
from contracts.silver import CleanPost
from contracts.gold import EnrichedPost

__all__ = ["RawSocialPost", "CleanPost", "EnrichedPost"]
