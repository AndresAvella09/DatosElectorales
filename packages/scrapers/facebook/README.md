# Facebook Scraper

> ⚠️ **Pendiente de implementación.**

Este directorio contendrá el scraper de Facebook cuando el equipo lo construya.

## Requisitos esperados
- Definir la estrategia de scraping (API oficial, headless browser, etc.)
- Implementar la recolección de posts/comentarios relevantes al discurso electoral
- Documentar el proceso en este README con instrucciones de uso

## Salida esperada
El scraper debe producir un CSV o JSON con al menos los siguientes campos para ser mapeado al esquema Bronze (`RawSocialPost`):
- `id` — Identificador único del post
- `datetime` — Fecha y hora
- `username` — Autor
- `text` — Contenido textual
- Métricas de engagement (likes, comments, shares)
