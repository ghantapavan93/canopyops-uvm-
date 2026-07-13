#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for database..."
python - <<'PY'
import time, sys
from sqlalchemy import create_engine, text
from app.core.config import get_settings

url = get_settings().database_url
for attempt in range(30):
    try:
        create_engine(url).connect().execute(text("SELECT 1"))
        print("[entrypoint] database is up")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] db not ready ({attempt+1}/30): {exc}")
        time.sleep(2)
print("[entrypoint] database never became ready")
sys.exit(1)
PY

echo "[entrypoint] applying migrations..."
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] seeding synthetic data..."
  python -m app.seed
fi

echo "[entrypoint] starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
