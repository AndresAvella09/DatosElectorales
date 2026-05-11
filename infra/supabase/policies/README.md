# RLS Policies — Mirror legible

Las policies **canonicas** viven dentro de la migracion
`infra/supabase/migrations/20260509120700__rls_policies.sql`. Ese es el archivo
que aplica el CLI de Supabase (`supabase db push`).

Los archivos de esta carpeta son una **copia organizada por schema** para que
sea facil leer "que politica afecta a este schema sin abrir la migracion
completa". No se ejecutan por separado; si modificas algo aqui, debes reflejar
el cambio en la migracion (o, mejor, abrir una migracion nueva
`<timestamp>__<descripcion>.sql`).

## Modelo de seguridad (resumen)

| Schema  | service_role | anon | authenticated |
|---------|--------------|------|---------------|
| raw     | full         | -    | -             |
| silver  | full         | -    | -             |
| gold    | full         | -    | -             |
| ops     | full         | -    | -             |
| public  | full         | SELECT en `v_*` | SELECT en `v_*` |
| storage `bronze-raw` | full | - | - |
| storage `exports`    | full | - | - |

- **Default deny**: revocamos privilegios por defecto en `anon` y
  `authenticated` para schemas internos. Cualquier nueva tabla en `public` no
  expone datos hasta que demos `grant select` explicito.
- **service_role** se usa solo desde el pipeline (Prefect / FastAPI) con la
  service key cargada por env. Nunca desde el front.
- **Storage**: ambos buckets son privados; las URLs firmadas se generan desde
  el backend.

## Cambiar una policy

1. Crear una migracion nueva: `supabase migration new tighten_<nombre>`.
2. En esa migracion: `drop policy if exists ...; create policy ...`.
3. Actualizar el archivo de mirror correspondiente en esta carpeta.
4. PR contra `main` con la migracion + diff del mirror.
