#!/usr/bin/env bash
# 업로드 기반 에이전트 시험 (B.40) — 별도 스택(-p nhdipe2e, 포트 3100)을 새로 띄워 2026.09 시험 파일을 올리고 결과를 확인한 뒤 내린다.
# 기본 스택(운영 · 로컬 DB)은 건드리지 않는다. 이미지는 기본 스택과 같은 nhdip/api · nhdip/web 을 쓴다(먼저 make up 또는 docker compose build).
#   make upload-test                              # LLM 없이(규칙 판단 · 기존 문장)
#   E2E_LLM_BASE=https://…/v1 E2E_LLM_KEY=… E2E_LLM_MODEL=claude-sonnet-5 E2E_LLM_EMBED=amazon.titan-embed-text-v2:0 make upload-test
#   KEEP=1 make upload-test                       # 끝난 뒤 스택을 남겨 http://localhost:3100 에서 화면 확인 (정리: docker compose -p nhdipe2e down -v)
# 결과: ${E2E_OUT:-/tmp/nhdip-upload}/upload-agents.{md,json}
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
P=nhdipe2e
export WEB_PORT=${E2E_WEB_PORT:-3100} API_PORT=${E2E_API_PORT:-8100} NEO4J_HTTP_PORT=${E2E_NEO4J_HTTP_PORT:-7574} NEO4J_BOLT_PORT=${E2E_NEO4J_BOLT_PORT:-7787} ES_PORT=${E2E_ES_PORT:-9300}
FIX="${TMPDIR:-/tmp}/nhdip-upload-fixtures"
cleanup() { [[ "${KEEP:-0}" == "1" ]] || docker compose -p "$P" down -v >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "[upload-test] 별도 스택 기동 (${P} · 웹 ${WEB_PORT})"
docker compose -p "$P" down -v >/dev/null 2>&1 || true
docker compose -p "$P" up -d >/dev/null
for _ in $(seq 1 90); do
  st=$(docker compose -p "$P" ps --format '{{.Service}}={{.Health}}' | tr '\n' ' ')
  [[ "$st" == *"api=healthy"* && "$st" == *"worker=healthy"* && "$st" == *"web=healthy"* ]] && break
  sleep 5
done
docker compose -p "$P" exec -T api python -m nhdip.cli wait-idle --timeout 900
echo "[upload-test] 시험 파일 생성"
rm -rf "$FIX" && mkdir -p "$FIX"
docker compose -p "$P" run --rm -T --no-deps -v "$PWD/apps/e2e/fixtures:/fx:ro" -v "$FIX:/out" -e OUT=/out api python /fx/make_upload_fixtures.py
echo "[upload-test] 업로드 · 흐름 확인"
cd apps/e2e && npm install --no-audit --no-fund >/dev/null
E2E_BASE="http://localhost:${WEB_PORT}" E2E_ADMIN_EMP="$BOOTSTRAP_ADMIN_EMP_NO" E2E_ADMIN_PW="$BOOTSTRAP_ADMIN_PASSWORD" FIXTURES="$FIX" E2E_OUT="${E2E_OUT:-/tmp/nhdip-upload}" node upload-agents.mjs
