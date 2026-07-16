#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for database..."
python - <<'PY'
import time, sys
from sqlalchemy import create_engine, text
from app.core.config import get_settings

# Use the admin URL — the app role may not exist until migrations run.
url = get_settings().effective_admin_url
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

WORKERS="${WEB_CONCURRENCY:-1}"
# Bind the port the platform assigns (Render/Railway/Fly inject $PORT); fall back
# to 8000 for docker-compose, where the port is fixed by the compose file.
PORT="${PORT:-8000}"
echo "[entrypoint] starting API on :${PORT} with ${WORKERS} worker(s)..."
# The API is stateless (session-per-request; shared state lives in Postgres),
# so it scales horizontally across workers/replicas with no sticky sessions.
# --timeout-graceful-shutdown lets in-flight requests drain on deploy/rollout.
exec uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT}" \
  --workers "${WORKERS}" \
  --timeout-graceful-shutdown 20
