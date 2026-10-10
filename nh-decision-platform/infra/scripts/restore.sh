#!/usr/bin/env bash
# 복구 (B.32) — backup.sh 로 만든 폴더에서 PostgreSQL · 파일 저장소를 되살린다. 현재 데이터를 덮어쓴다.
#   make restore FROM=backups/20261010-120000 CONFIRM=yes
# 복구 후 관리자 [온톨로지] 재투영(또는 wf_graph_projection 실행)으로 Neo4j 그래프를 다시 만든다.
set -euo pipefail
cd "$(dirname "$0")/../.."
FROM="${FROM:?FROM=백업 폴더 경로가 필요합니다}"
if [[ "${CONFIRM:-}" != "yes" ]]; then
  echo "현재 DB · 파일을 ${FROM} 내용으로 덮어씁니다. 계속하려면 CONFIRM=yes 를 붙여 다시 실행하세요." >&2
  exit 2
fi
set -a; . ./.env; set +a
DB="${POSTGRES_DB:-nhdip}"
USER_="${POSTGRES_USER:-nhdip}"
[[ -f "${FROM}/SHA256SUMS" ]] && ( cd "$FROM" && shasum -a 256 -c SHA256SUMS )
echo "[restore] api · worker 중지"
docker compose stop api worker web
echo "[restore] postgres ${DB}"
docker compose exec -T postgres pg_restore -U "$USER_" -d "$DB" --clean --if-exists --no-owner < "${FROM}/${DB}.dump"
if [[ -f "${FROM}/litellm.dump" ]]; then
  echo "[restore] postgres litellm"
  docker compose stop litellm
  docker compose exec -T postgres pg_restore -U "$USER_" -d litellm --clean --if-exists --no-owner < "${FROM}/litellm.dump"
  docker compose start litellm
fi
echo "[restore] filestore"
docker compose run --rm --no-deps -T --entrypoint sh api -c 'rm -rf /data/files/* && tar -xzf - -C /data/files' < "${FROM}/filestore.tar.gz"
docker compose start api worker web
echo "[restore] 완료 — 관리자 [온톨로지] 재투영으로 그래프를 다시 만드세요"
