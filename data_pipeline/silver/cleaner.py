"""
cleaner.py — Deduplicación y normalización de texto para la capa Silver.

Qué hace:
  1. Deduplicación por ID (marca duplicados, no los elimina).
  2. Normalización: lowercase, elimina URLs, @menciones, #hashtags.
  3. Detección básica de idioma español por keywords.
  4. Preserva emojis (señales de sentimiento).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "packages"))

from contracts.bronze import RawSocialPost  # noqa: E402
from logger import get_logger  # noqa: E402

log = get_logger("silver.cleaner")

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"@\w+")
_HASHTAG_RE = re.compile(r"#\w+")
_MULTI_SPACE = re.compile(r"\s+")
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U00002700-\U000027BF\U0001F900-\U0001FAFF]+",
    flags=re.UNICODE,
)

_ES_KEYWORDS = {
    "de", "la", "el", "en", "los", "las", "un", "una", "por", "con",
    "para", "que", "del", "al", "se", "es", "no", "su", "más", "pero",
    "colombia", "país", "gobierno", "presidente", "candidato",
}


def normalize_text(text: str) -> dict:
    """Normaliza texto y extrae metadatos (has_hashtags, has_emojis, has_urls)."""
    if not text:
        return {"text_clean": "", "has_hashtags": False, "has_emojis": False, "has_urls_original": False}

    has_urls = bool(_URL_RE.search(text))
    has_hashtags = bool(_HASHTAG_RE.search(text))
    has_emojis = bool(_EMOJI_RE.search(text))

    clean = _URL_RE.sub("", text)
    clean = _MENTION_RE.sub("", clean)
    clean = _HASHTAG_RE.sub("", clean)
    clean = _MULTI_SPACE.sub(" ", clean.lower()).strip()

    return {"text_clean": clean, "has_hashtags": has_hashtags, "has_emojis": has_emojis, "has_urls_original": has_urls}


def detect_language(text: str) -> str | None:
    """Detección básica de español por keywords. Reemplazar por langdetect en producción."""
    if not text or len(text.strip()) < 3:
        return None
    words = set(text.lower().split())
    if len(words) > 0 and (len(words & _ES_KEYWORDS) / len(words)) >= 0.10:
        return "es"
    return "unknown"


def deduplicate(posts: list[RawSocialPost], existing_ids: set[str] | None = None):
    """Elimina duplicados por ID. Returns (unique_posts, duplicate_ids)."""
    seen = set(existing_ids or set())
    unique, dup_ids = [], []
    for post in posts:
        if post.id in seen:
            dup_ids.append(post.id)
        else:
            seen.add(post.id)
            unique.append(post)
    if dup_ids:
        log.info("Dedup: %d duplicados de %d total", len(dup_ids), len(posts))
    return unique, dup_ids


def clean_posts(posts: list[RawSocialPost], existing_ids: set[str] | None = None) -> list[dict]:
    """Pipeline: dedup + normalización + idioma. Retorna dicts parciales para CleanPost."""
    unique_posts, dup_ids = deduplicate(posts, existing_ids)
    results = []
    for post in unique_posts:
        info = normalize_text(post.text)
        lang = detect_language(post.text)
        results.append({
            "id": post.id, "source": post.source, "source_id": post.source_id,
            "datetime_utc": post.datetime_utc, "text_original": post.text,
            "text_clean": info["text_clean"], "parent_id": post.parent_id,
            "engagement": post.engagement, "metadata": post.metadata,
            "lang": lang, "is_duplicate": False,
            "has_hashtags": info["has_hashtags"], "has_emojis": info["has_emojis"],
            "has_urls_original": info["has_urls_original"],
        })
    log.info("Limpieza: %d registros procesados", len(results))
    return results
