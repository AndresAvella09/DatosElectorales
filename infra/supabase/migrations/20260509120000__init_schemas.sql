-- Migration: init_schemas
-- Crea los schemas de la arquitectura medallion + ops.
-- Public ya existe por defecto; aqui solo nos aseguramos de los demas.

create schema if not exists raw;
create schema if not exists silver;
create schema if not exists gold;
create schema if not exists ops;

comment on schema raw    is 'Bronze: metadatos de archivos crudos en Storage. Escribe pipeline (service_role).';
comment on schema silver is 'Silver: posts limpios y anonimizados. Escribe pipeline (service_role).';
comment on schema gold   is 'Gold: features listas para consumo. Escribe pipeline (service_role).';
comment on schema ops    is 'Operacional: pipeline_runs, quality_reports, alertas.';

-- Roles base de Supabase: anon, authenticated, service_role.
-- Por defecto QUITAMOS USAGE en los schemas internos: solo service_role los toca.
revoke all on schema raw    from public, anon, authenticated;
revoke all on schema silver from public, anon, authenticated;
revoke all on schema gold   from public, anon, authenticated;
revoke all on schema ops    from public, anon, authenticated;

grant usage on schema raw    to service_role;
grant usage on schema silver to service_role;
grant usage on schema gold   to service_role;
grant usage on schema ops    to service_role;

-- Default privileges para que tablas futuras hereden los permisos correctos.
alter default privileges in schema raw    grant all on tables to service_role;
alter default privileges in schema silver grant all on tables to service_role;
alter default privileges in schema gold   grant all on tables to service_role;
alter default privileges in schema ops    grant all on tables to service_role;

-- Extensiones necesarias.
create extension if not exists pgcrypto;     -- gen_random_uuid()
create extension if not exists "uuid-ossp";  -- compat
