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
    # 마이그레이션 · 시드 · 앱 계정 준비는 소유자 계정으로 (B.33 — NHDIP_USE_APP_ROLE=0)
    if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
      echo "[entrypoint] alembic upgrade head"
      NHDIP_USE_APP_ROLE=0 alembic upgrade head
    fi
    if [[ -n "${APP_DB_PASSWORD:-}" ]]; then
      echo "[entrypoint] API 전용 DB 계정 준비 (${APP_DB_USER:-nhdip_app})"
      NHDIP_USE_APP_ROLE=0 python -m nhdip.cli db-app-role || {
        echo "[entrypoint] 경고: 앱 계정 준비 실패 — 이번 기동은 소유자 계정으로 접속합니다" >&2
        export NHDIP_USE_APP_ROLE=0
      }
    fi
    if [[ "${SEED_ON_START:-0}" == "1" ]]; then
      echo "[entrypoint] seeding master + simulated data"
      NHDIP_USE_APP_ROLE=0 python -m nhdip.cli seed --with-precompute || echo "[entrypoint] seed skipped/failed (계속 진행)"
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
