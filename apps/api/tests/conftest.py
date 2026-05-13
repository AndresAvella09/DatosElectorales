"""Asegura que `apps.api` se importe desde la raiz del repo."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
