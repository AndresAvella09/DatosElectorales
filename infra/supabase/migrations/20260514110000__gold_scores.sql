-- Migration: gold.scores_candidato_red + gold.parlamentarias_partido_red
-- Scores de sentimiento/engagement por candidato y red social.
-- Carga directa desde EDA — no pasan por bronze/silver.

create table if not exists gold.scores_candidato_red (
  entidad          text        not null,
  red              text        not null,
  ventana          int         not null,
  fecha_ini_ventana date,
  fecha_fin_ventana date,
  score_final      numeric(10,6),
  score_promedio   numeric(10,6),
  menciones        numeric(10,2),
  engagement_total numeric(14,2),
  loaded_at        timestamptz not null default now(),
  primary key (entidad, red, ventana)
);

create index if not exists gold_scores_entidad_idx
  on gold.scores_candidato_red (entidad, ventana);

create index if not exists gold_scores_red_idx
  on gold.scores_candidato_red (red, ventana);

comment on table gold.scores_candidato_red is
  'Scores de sentimiento y engagement por candidato x red social x ventana temporal.';


create table if not exists gold.parlamentarias_partido_red (
  entidad          text        not null,
  red              text        not null,
  ventana          int         not null,
  fecha_ini_ventana date,
  fecha_fin_ventana date,
  score_final      numeric(10,6),
  score_promedio   numeric(10,6),
  menciones        numeric(10,2),
  engagement_total numeric(14,2),
  loaded_at        timestamptz not null default now(),
  primary key (entidad, red, ventana)
);

create index if not exists gold_parl_entidad_idx
  on gold.parlamentarias_partido_red (entidad, ventana);

comment on table gold.parlamentarias_partido_red is
  'Scores de sentimiento y engagement por partido parlamentario x red social x ventana.';


grant all on gold.scores_candidato_red to service_role;
grant all on gold.parlamentarias_partido_red to service_role;
grant select on gold.scores_candidato_red to authenticated, anon;
grant select on gold.parlamentarias_partido_red to authenticated, anon;
