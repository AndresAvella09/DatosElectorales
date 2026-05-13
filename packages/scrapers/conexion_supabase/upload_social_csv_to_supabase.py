import csv
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

try:
    from supabase.client import ClientOptions
except ImportError:
    from supabase.lib.client_options import ClientOptions


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_AUTH_EMAIL = os.getenv("SUPABASE_AUTH_EMAIL")
SUPABASE_AUTH_PASSWORD = os.getenv("SUPABASE_AUTH_PASSWORD")

SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "raw")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "social_scraping_uploads")

SOURCE = os.getenv("SOURCE", "test").strip().lower()
CSV_PATH = os.getenv("CSV_PATH", "data/raw/tweets_colombia.csv")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))

RUN_ID = os.getenv("RUN_ID") or str(uuid.uuid4())


def require_env(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(f"Falta la variable de entorno: {name}")
    return value


def read_csv_rows(path: str) -> list[dict]:
    csv_path = Path(path)

    if not csv_path.exists():
        raise FileNotFoundError(f"No existe el CSV: {csv_path}")

    rows = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise RuntimeError("El CSV no tiene encabezados.")

        for index, row in enumerate(reader, start=1):
            clean_payload = {
                key: (None if value == "" else value)
                for key, value in row.items()
            }

            rows.append(
                {
                    "run_id": RUN_ID,
                    "source": SOURCE,
                    "original_filename": csv_path.name,
                    "row_number": index,
                    "payload": clean_payload,
                }
            )

    return rows


def get_client():
    url = require_env("SUPABASE_URL", SUPABASE_URL)
    anon_key = require_env("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY)
    email = require_env("SUPABASE_AUTH_EMAIL", SUPABASE_AUTH_EMAIL)
    password = require_env("SUPABASE_AUTH_PASSWORD", SUPABASE_AUTH_PASSWORD)

    client = create_client(
        url,
        anon_key,
        options=ClientOptions(schema=SUPABASE_SCHEMA),
    )

    auth_response = client.auth.sign_in_with_password(
        {
            "email": email,
            "password": password,
        }
    )

    if not auth_response.user:
        raise RuntimeError("No se pudo iniciar sesión en Supabase Auth.")

    print(f"[auth] Login OK as: {auth_response.user.email}")
    print(f"[auth] User UID: {auth_response.user.id}")
    print(f"[auth] Schema: {SUPABASE_SCHEMA}")
    print(f"[auth] Table: {SUPABASE_TABLE}")
    print(f"[csv] Source: {SOURCE}")
    print(f"[run] RUN_ID: {RUN_ID}")

    return client


def insert_batches(client, rows: list[dict]) -> int:
    total = 0

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]

        client.schema(SUPABASE_SCHEMA).table(SUPABASE_TABLE).insert(batch).execute()

        total += len(batch)
        print(f"[upload] {total}/{len(rows)} rows uploaded")

    return total


def main():
    print("[step] Reading CSV...")
    rows = read_csv_rows(CSV_PATH)
    print(f"[csv] {CSV_PATH}: {len(rows)} rows loaded")

    print("[step] Connecting to Supabase...")
    client = get_client()

    print("[step] Uploading rows...")
    uploaded = insert_batches(client, rows)

    print("[done] Upload finished")
    print(f"[done] Rows uploaded: {uploaded}")
    print(f"[done] RUN_ID: {RUN_ID}")

    try:
        result = (
            client.schema(SUPABASE_SCHEMA)
            .table(SUPABASE_TABLE)
            .select("id", count="exact")
            .eq("run_id", RUN_ID)
            .execute()
        )

        print(f"[verify] Rows visible to this user for this RUN_ID: {result.count}")
    except Exception as exc:
        print("[verify] Could not run SELECT verification.")
        print(f"[verify] Reason: {exc}")


if __name__ == "__main__":
    main()
