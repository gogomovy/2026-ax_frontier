#!/usr/bin/env bash
# 백업 (B.32) — PostgreSQL(업무 DB + litellm DB) 덤프 + 파일 저장소(업로드 원본) 묶음.
# Neo4j 그래프는 PostgreSQL 원장에서 다시 만들 수 있으므로(관리자 [온톨로지] 재투영) 백업하지 않는다.
#   make backup                 → backups/<시각>/
#   BACKUP_DIR=/mnt/bk make backup
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
TS="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR:-backups}/${TS}"
mkdir -p "$OUT"
DB="${POSTGRES_DB:-nhdip}"
USER_="${POSTGRES_USER:-nhdip}"
echo "[backup] postgres ${DB} → ${OUT}/${DB}.dump"
docker compose exec -T postgres pg_dump -U "$USER_" -d "$DB" -Fc > "${OUT}/${DB}.dump"
if docker compose exec -T postgres psql -U "$USER_" -d "$DB" -tAc "SELECT 1 FROM pg_database WHERE datname='litellm'" | grep -q 1; then
  echo "[backup] postgres litellm → ${OUT}/litellm.dump"
  docker compose exec -T postgres pg_dump -U "$USER_" -d litellm -Fc > "${OUT}/litellm.dump"
fi
echo "[backup] filestore → ${OUT}/filestore.tar.gz"
docker compose exec -T api tar -czf - -C /data/files . > "${OUT}/filestore.tar.gz"
( cd "$OUT" && shasum -a 256 ./* > SHA256SUMS )
chmod -R go-rwx "$OUT"
echo "[backup] 완료: ${OUT}"
ls -la "$OUT"
