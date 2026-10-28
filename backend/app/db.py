"""Postgres / Supabase storage, used when DATABASE_URL is set in backend/.env.

Each dataset size lives in its own schema (shrinkage_small, shrinkage_full), outside Supabase's public
schema, so none of it is exposed through Supabase's auto-generated REST API.

    python -m app.db --size full      # load a finished run (backend/output/full) into Postgres

The load builds a fresh `<schema>_loading` schema, bulk-copies every CSV, adds all foreign keys (which
re-validates every row), then swaps it in within one transaction. Readers never see a half-loaded run.
"""
import argparse
import datetime
import decimal
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
import psycopg2.pool

from app import settings
from app.pipeline.config import SIZES
from app.pipeline.schema import PG_TABLES, pg_ddl

ALERT_TABLES = {"shrinkage_alert", "alert_evidence", "investigation"}


class NotAvailable(LookupError):
    pass


def enabled():
    return bool(settings.DATABASE_URL)


def schema(size):
    return f"{settings.DB_SCHEMA_PREFIX}_{size}"


# ---------- connections ----------
_pool, _pool_lock = None, threading.Lock()


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = psycopg2.pool.ThreadedConnectionPool(1, 8, settings.DATABASE_URL, connect_timeout=10)
        return _pool


def _reset_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
        _pool = None


@contextmanager
def _cursor(size=None):
    pool = _get_pool()
    con = pool.getconn()
    try:
        with con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:   # commit or roll back
            if size:
                cur.execute(f"SET LOCAL search_path TO {schema(size)}")
            yield cur
    finally:
        pool.putconn(con)


def _clean(v):   # same JSON shapes as the SQLite path
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def query(size, sql, params=()):
    """Run SQL written with ? placeholders (shared with SQLite) inside the size's schema."""
    sql = sql.replace("?", "%s")
    for attempt in (1, 2):   # Supabase's pooler drops idle connections; retry once on a fresh pool
        try:
            with _cursor(size) as cur:
                cur.execute(sql, list(params))
                return [{k: _clean(v) for k, v in r.items()} for r in cur.fetchall()]
        except psycopg2.errors.UndefinedTable:
            raise NotAvailable(f"No '{size}' data in the database yet. Run the pipeline or `python -m app.db --size {size}`.")
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            _reset_pool()
            if attempt == 2:
                raise


def available(size):
    try:
        with _cursor() as cur:
            cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = 'pipeline_report'",
                        (schema(size),))
            return cur.fetchone() is not None
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        _reset_pool()
        return False


def report(size, name):
    rows = query(size, "SELECT body FROM pipeline_report WHERE name = ?", (name,))
    return rows[0]["body"] if rows else None


def ground_truth(size):
    return pd.DataFrame(query(size, "SELECT * FROM ground_truth ORDER BY gt_id")).fillna("")


# ---------- bulk load ----------
def _csv_for(folder, table):
    if table == "ground_truth":
        return folder / "ground_truth" / "csv" / "anomalies.csv"
    return folder / ("alerts" if table in ALERT_TABLES else "data") / "csv" / f"{table}.csv"


def load(size, folder, say=print):
    folder = Path(folder)
    if not (folder / "reports" / "manifest.json").exists():
        raise FileNotFoundError(f"{folder} has no finished run; run the pipeline first.")
    final, tmp = schema(size), schema(size) + "_loading"
    create, keys = pg_ddl()
    t0 = time.time()
    con = psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)
    try:
        with con, con.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute(f"DROP SCHEMA IF EXISTS {tmp} CASCADE; CREATE SCHEMA {tmp}; SET LOCAL search_path TO {tmp};")
            cur.execute(create)
            for name, t in PG_TABLES.items():
                cols = ", ".join(c["name"] for c in t["cols"])
                with open(_csv_for(folder, name), encoding="utf-8") as f:
                    cur.copy_expert(f"COPY {name} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)", f)
                say(f"  [{time.time() - t0:5.1f}s] {name}: {cur.rowcount:,} rows")
            for rep in sorted((folder / "reports").glob("*.json")):
                cur.execute("INSERT INTO pipeline_report (name, body) VALUES (%s, %s)", (rep.stem, rep.read_text(encoding="utf-8")))
            cur.execute(keys)
            say(f"  [{time.time() - t0:5.1f}s] primary + foreign keys valid, indexes built")
            cur.execute(f"DROP SCHEMA IF EXISTS {final} CASCADE; ALTER SCHEMA {tmp} RENAME TO {final};")
            cur.execute("SELECT pg_size_pretty(SUM(pg_total_relation_size(c.oid))) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relkind = 'r'", (final,))
            size_on_disk = cur.fetchone()[0]
    finally:
        con.close()
    _reset_pool()
    say(f"  [{time.time() - t0:5.1f}s] loaded into schema '{final}' ({size_on_disk})")
    return size_on_disk


if __name__ == "__main__":
    from app.pipeline.run import OUTPUT_ROOT

    ap = argparse.ArgumentParser(description="Load a finished pipeline run into Postgres / Supabase.")
    ap.add_argument("--size", choices=list(SIZES), default="small")
    args = ap.parse_args()
    if not enabled():
        raise SystemExit("Set DATABASE_URL in backend/.env first (Supabase: Connect -> Session pooler URI).")
    load(args.size, OUTPUT_ROOT / args.size)
