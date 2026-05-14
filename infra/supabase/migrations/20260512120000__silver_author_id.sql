-- Migration: silver.posts — renombrar username_hash → author_id
--
-- Motivo: username_hash era redundante (siempre null en la práctica porque
-- cleaner.py nunca pasaba el campo username al dict de salida) y conceptualmente
-- incorrecto (los CSV fuente ya llegan con usernames pseudoanónimos, no hay
-- nada que hashear). author_id es el ID de plataforma del autor:
--   Twitter  → username ya anonimizado (twitter_user_xxx)
--   TikTok   → user_unique_id (ID interno de TikTok)
--   YouTube  → yt_user_xxx (ya anonimizado)
--   Facebook → null (los datos no contienen usuario)

alter table silver.posts rename column username_hash to author_id;

comment on column silver.posts.author_id is
  'ID del autor en la plataforma. Pseudoanónimo por diseño: user_unique_id en TikTok, '
  'yt_user_xxx en YouTube, twitter_user_xxx en Twitter. Null para Facebook.';
