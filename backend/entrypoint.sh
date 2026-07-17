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

# Prove the APP can connect — not just the admin role.
#
# The wait above uses ADMIN_DATABASE_URL, because the app role does not exist
# until migrations run. That means it proves the database is reachable by a role
# the app never uses, and everything below it can be perfectly healthy while the
# app itself cannot read a single row. That is exactly what happened on the first
# Neon deploy: migrations applied, seed succeeded, Render reported "live", and
# every request 500'd because the pooled endpoint rejected the engine's
# `options=-c statement_timeout=...` startup parameter.
#
# So: connect through build_engine() — the same factory the app uses, with the
# same connect_args — and fail the deploy loudly rather than going live broken.
echo "[entrypoint] verifying the app role can connect..."
python - <<'PY'
import sys
from sqlalchemy import text
from app.core.database import build_engine
from app.core.config import get_settings

url = get_settings().database_url
try:
    with build_engine().connect() as conn:
        who = conn.execute(text("SELECT current_user")).scalar()
    print(f"[entrypoint] app role connected as {who}")
except Exception as exc:  # noqa: BLE001
    host = url.rsplit("@", 1)[-1].split("/")[0]  # never print the password
    print(f"[entrypoint] APP ROLE CANNOT CONNECT to {host}\n  {exc}")
    print("[entrypoint] Refusing to start: the API would report healthy and 500 "
          "every request. If this says 'unsupported startup parameter in "
          "options', DATABASE_URL is a POOLED endpoint — use the direct host "
          "(no '-pooler'). See docs/DEPLOY.md.")
    sys.exit(1)
PY

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
