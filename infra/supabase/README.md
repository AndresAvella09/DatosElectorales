# Supabase — DatosElectorales

Esta carpeta contiene **todo** lo que define el warehouse en Supabase: schemas,
tablas, vistas, RLS y storage. Es la fuente de verdad del modelo de datos.

```
infra/supabase/
├── migrations/         # SQL versionado (lo que aplica supabase CLI)
├── policies/           # Mirror legible de RLS por schema (no ejecutable)
├── seed.sql            # Datos demo para `supabase db reset`
└── README.md           # Este archivo
```

## Capas

| Schema   | Contenido                                | Acceso        |
|----------|------------------------------------------|---------------|
| `raw`    | Bronze: metadatos de archivos crudos     | service_role  |
| `silver` | Posts limpios + anonimizados (particion) | service_role  |
| `gold`   | Features para consumo + slots ML         | service_role  |
| `ops`    | pipeline_runs, quality_reports, alerts   | service_role  |
| `public` | Vistas `v_*` consumidas por el front     | anon + auth   |

Storage:

| Bucket       | Uso                                       | Acceso        |
|--------------|-------------------------------------------|---------------|
| `bronze-raw` | CSV/JSON crudos del scraper               | service_role  |
| `exports`    | Reportes de calidad / dumps semanales     | service_role  |

Vistas publicas (lo unico que ve el front):

- `public.v_sentiment_daily` — matview, sentiment diario por fuente.
- `public.v_pipeline_health` — view, ultimas 50 corridas.
- `public.v_sources_volume_7d` — view, volumen por fuente / dia (7 dias).
- `public.v_last_success_by_flow` — view, ultima corrida exitosa por flow.

## Aplicar localmente

Requisito: [Supabase CLI](https://supabase.com/docs/guides/cli) y Docker
corriendo.

```bash
# 1. Levantar Supabase local (Postgres + Studio + Storage)
supabase start

# 2. Aplicar todas las migraciones de cero + seed
supabase db reset
```

Esto deja una instancia en `http://localhost:54323` (Studio).

### Sin Supabase CLI (solo Postgres)

```bash
psql "$SUPABASE_DB_URL" -f infra/supabase/migrations/20260509120000__init_schemas.sql
psql "$SUPABASE_DB_URL" -f infra/supabase/migrations/20260509120100__raw_posts.sql
# ... aplicar en orden
```

## Aplicar a prod

```bash
supabase db push --db-url "$SUPABASE_DB_URL"
```

CI valida el lint antes del merge:

```bash
supabase db lint
```

## Crear nueva migracion

```bash
supabase migration new <descripcion_corta>
```

Esto genera `infra/supabase/migrations/<timestamp>__<descripcion>.sql`. Toda
alteracion de schema (nueva tabla, nueva columna, nueva policy) **debe** ir
como migracion nueva. **Nunca** editar una migracion ya aplicada.

## Verificar el hito H1

```sql
-- Schemas existen
select nspname from pg_namespace where nspname in ('raw','silver','gold','ops');

-- Tablas mininas
select 'raw.posts'::regclass, 'silver.posts'::regclass,
       'gold.features'::regclass, 'ops.pipeline_runs'::regclass,
       'ops.quality_reports'::regclass;

-- Al menos una vista public.v_*
select matviewname from pg_matviews where schemaname = 'public';
select viewname    from pg_views    where schemaname = 'public' and viewname like 'v\_%';

-- Buckets
select id from storage.buckets where id in ('bronze-raw', 'exports');
```
