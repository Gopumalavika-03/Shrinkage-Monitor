"""Environment settings, read once from backend/.env (variables already set in the shell win).

Template: backend/.env.example. Every setting has a working default, so .env is optional.
"""
import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env(BACKEND / ".env")


def get(key, default=""):
    return os.environ.get(key) or default


def _path(value):
    p = Path(value)
    return p if p.is_absolute() else BACKEND / p   # relative paths are relative to backend/


API_HOST = get("API_HOST", "127.0.0.1")
API_PORT = int(get("API_PORT", "8000"))
API_RELOAD = get("API_RELOAD", "false").lower() == "true"
CORS_ORIGINS = [o.strip() for o in get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
OUTPUT_DIR = _path(get("OUTPUT_DIR", "output"))
# Postgres / Supabase. Empty = the API reads each run's local SQLite file instead.
DATABASE_URL = get("DATABASE_URL")
DB_SCHEMA_PREFIX = get("DB_SCHEMA_PREFIX", "shrinkage")   # one schema per size: shrinkage_small, shrinkage_full
