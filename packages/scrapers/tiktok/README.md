# TikTok Scraper

> ⚠️ **Pendiente de implementación.**

Este directorio contendrá el scraper de TikTok cuando el equipo lo construya.

## Requisitos esperados
- Definir la estrategia de scraping (API oficial, headless browser, etc.)
- Implementar la recolección de videos/comentarios relevantes al discurso electoral
- Documentar el proceso en este README con instrucciones de uso

## Salida esperada
El scraper debe producir un CSV o JSON con al menos los siguientes campos para ser mapeado al esquema Bronze (`RawSocialPost`):
- `id` — Identificador único del post/video
- `datetime` — Fecha y hora
- `username` — Autor
- `text` — Contenido textual (caption, comentario)
- Métricas de engagement (likes, comments, shares, views)
