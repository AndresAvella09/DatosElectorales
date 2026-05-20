"""
apply_migrations.py — Aplica migraciones SQL versionadas contra Supabase.

Lee SUPABASE_DB_URL del .env (Settings -> Database -> Connection string -> URI),
crea la tabla `_migrations_applied` si no existe, y corre cada .sql en
`infra/supabase/migrations/` que aun no haya sido aplicado.

Idempotente: re-correr no vuelve a aplicar las que ya estan en la tabla.

Uso:
    uv run python infra/supabase/apply_migrations.py
    uv run python infra/supabase/apply_migrations.py --dry-run
    uv run python infra/supabase/apply_migrations.py --only 20260510120000__raw_videos.sql
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[1]
MIGRATIONS_DIR = _THIS_DIR / "migrations"

load_dotenv(_REPO_ROOT / ".env")


_BOOTSTRAP_SQL = """
create table if not exists public._migrations_applied (
  filename    text primary key,
  applied_at  timestamptz not null default now(),
  sha256      text
);
revoke all on table public._migrations_applied from anon, authenticated;
"""


def _sha256(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _list_migrations() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return files


def _connect() -> psycopg.Connection:
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        print(
            "ERROR: SUPABASE_DB_URL no definido en .env.\n"
            "  Sacalo de Supabase Studio -> Settings -> Database -> "
            "Connection string -> URI (con tu password).",
            file=sys.stderr,
        )
        sys.exit(2)
    # autocommit=True para que cada migracion confirme por si misma.
    return psycopg.connect(url, autocommit=True)


def _applied_set(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("select filename from public._migrations_applied")
        return {r[0] for r in cur.fetchall()}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="apply_migrations")
    p.add_argument("--dry-run", action="store_true",
                   help="Mostrar que se aplicaria sin ejecutar.")
    p.add_argument("--only", default=None,
                   help="Aplicar solo el filename indicado (debe existir).")
    args = p.parse_args(argv)

    files = _list_migrations()
    if not files:
        print("No hay migraciones en", MIGRATIONS_DIR)
        return 0

    if args.dry_run:
        print("DRY-RUN. Connectando para checar estado...")

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_BOOTSTRAP_SQL)
        applied = _applied_set(conn)
        print(f"Ya aplicadas: {len(applied)}")
        for a in sorted(applied):
            print(f"  [done] {a}")

        pending = [f for f in files if f.name not in applied]
        if args.only:
            target = next((f for f in files if f.name == args.only), None)
            if target is None:
                print(f"ERROR: --only {args.only} no existe")
                return 2
            if target.name in applied:
                print(f"  [skip] {target.name} ya aplicada")
                return 0
            pending = [target]

        if not pending:
            print("Todo al dia.")
            return 0

        print(f"\nA aplicar: {len(pending)}")
        for f in pending:
            print(f"  [todo] {f.name}")

        if args.dry_run:
            print("\nDRY-RUN: no se ejecuto nada.")
            return 0

        print()
        for f in pending:
            sha = _sha256(f)
            print(f"  >>> Applying {f.name} (sha={sha[:12]})...")
            sql = f.read_text(encoding="utf-8")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "insert into public._migrations_applied "
                        "(filename, sha256) values (%s, %s)",
                        (f.name, sha),
                    )
                print(f"  <<< OK {f.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"  !!! FAIL {f.name}: {exc}")
                return 1

        print(f"\nAplicadas: {len(pending)}.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
