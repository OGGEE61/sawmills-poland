"""The four datasets the dashboard reads. One PostgreSQL table per CSV in data/processed, named after the file."""
from pathlib import Path

import psycopg

PROCESSED = Path(__file__).resolve().parents[2] / "data" / "processed"
TABLES = ("tartaki_ceidg", "tartaki_full", "verification", "leads")


def connect():
    """Connection settings come from the PG* environment variables (PGHOST, PGUSER, PGPASSWORD, PGDATABASE)."""
    return psycopg.connect(connect_timeout=10)
