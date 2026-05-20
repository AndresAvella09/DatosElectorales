-- Migration: media.momentum
-- Tabla independiente para momentum.csv.

create table if not exists media.momentum (
  fecha          date        not null,
  medio          text        not null,
  candidato      text        not null,
  menciones      int,
  share_of_voice numeric(8,6),
  rolling_7      numeric(10,4),
  momentum       numeric(10,4),
  loaded_at      timestamptz not null default now(),
  primary key (fecha, medio, candidato)
);

create index if not exists media_momentum_candidato_fecha_idx
  on media.momentum (candidato, fecha desc);

create index if not exists media_momentum_medio_fecha_idx
  on media.momentum (medio, fecha desc);

comment on table media.momentum is
  'Momentum de candidatos en medios por (fecha, medio, candidato). Fuente: momentum.csv';

grant all on media.momentum to service_role;
grant select on media.momentum to authenticated;
