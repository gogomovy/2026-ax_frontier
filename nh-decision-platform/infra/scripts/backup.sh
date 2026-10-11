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
if command -v sha256sum >/dev/null; then ( cd "$OUT" && sha256sum ./* > SHA256SUMS ); else ( cd "$OUT" && shasum -a 256 ./* > SHA256SUMS ); fi
chmod -R go-rwx "$OUT"
SIZE=$(du -sk "$OUT" | cut -f1)
# 운영 준비 점검의 '백업' 항목 — 감사 기록으로 남긴다
docker compose exec -T -e NHDIP_USE_APP_ROLE=0 api python -m nhdip.cli record-backup "$OUT" "$((SIZE * 1024))" >/dev/null || echo "[backup] 경고: 백업 기록 실패(백업 파일은 정상)" >&2
# 보관 개수 — 최근 BACKUP_KEEP 개만 남긴다(기본 14, 0 = 지우지 않음)
KEEP="${BACKUP_KEEP:-14}"
if [[ "$KEEP" -gt 0 ]]; then
  ALL=()
  while IFS= read -r d; do ALL+=("$d"); done < <(ls -1d "${BACKUP_DIR:-backups}"/[0-9]*-[0-9]* 2>/dev/null | sort)
  DROP=$(( ${#ALL[@]} - KEEP ))
  for (( i = 0; i < DROP; i++ )); do rm -rf -- "${ALL[$i]}" && echo "[backup] 오래된 백업 삭제: ${ALL[$i]}"; done
fi
echo "[backup] 완료: ${OUT}"
ls -la "$OUT"
