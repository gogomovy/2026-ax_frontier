#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-api}"

wait_for_db() {
  python - <<'PY'
import os, time, sys
import psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
for attempt in range(60):
    try:
        with psycopg.connect(url, connect_timeout=3):
            print("db ready", flush=True)
            sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"waiting for db ({attempt+1}): {exc}", flush=True)
        time.sleep(2)
sys.exit("database not reachable")
PY
}

case "$ROLE" in
  api)
    wait_for_db
    if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
      echo "[entrypoint] alembic upgrade head"
      alembic upgrade head
    fi
    if [[ "${SEED_ON_START:-0}" == "1" ]]; then
      echo "[entrypoint] seeding master + simulated data"
      python -m nhdip.cli seed --with-precompute || echo "[entrypoint] seed skipped/failed (계속 진행)"
    fi
    exec uvicorn nhdip.main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  worker)
    wait_for_db
    exec python -m nhdip.worker
    ;;
  scheduler)
    wait_for_db
    exec python -m nhdip.scheduler
    ;;
  migrate)
    wait_for_db
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
