#!/usr/bin/env bash
# Elasticsearch 인증 실패(HTTP 401 · unable to authenticate user [elastic]) 해결 — make es-password (Phase K · ES-02 · Q154)
#
# 원인: 내장 ES 는 ELASTIC_PASSWORD(= .env 의 ES_PASSWORD)를 볼륨(esdata)을 '처음 만들 때만' elastic 계정에 쓴다.
#       볼륨이 비밀번호 없이 · 다른 값으로 먼저 만들어졌거나 .env 를 다시 만들면 api · worker 는 401 을 받고 검색은 PostgreSQL 로 폴백한다.
# 하는 일 (데이터 유지 — 볼륨을 지우지 않는다. make reset 은 PostgreSQL 까지 지우므로 쓰지 않는다):
#   1) .env 의 ES_PASSWORD 확인(비어 있으면 make env 로 생성) → api · worker 를 .env 값으로 다시 만든다
#   2) ES 컨테이너에 임시 관리 계정(file realm superuser)을 만든다
#   3) api 컨테이너에서 그 계정으로 elastic 비밀번호를 ES_PASSWORD 로 바꾼다 (python -m nhdip.cli es-password)
#   4) 임시 계정을 지우고 api · worker 를 다시 시작해 새 연결로 점검(kb-es --check)
# 외부(사내) ES 를 쓰면 이 스크립트 대신 관리자 [AI 어시스턴트 색인 › 연결 설정]에서 주소 · 계정 · 비밀번호를 입력한다.
set -euo pipefail
cd "$(dirname "$0")/../.."
COMPOSE="${COMPOSE:-docker compose}"

[ -f .env ] || { echo "[es] .env 가 없습니다 — make env" >&2; exit 2; }
es_pw() { grep -E '^ES_PASSWORD=' .env | tail -1 | cut -d= -f2-; }
if [ -z "$(es_pw)" ]; then
  bash infra/scripts/ensure-env.sh >/dev/null
fi
[ -n "$(es_pw)" ] || { echo "[es] .env 의 ES_PASSWORD 를 만들지 못했습니다" >&2; exit 2; }

if ! $COMPOSE ps --status running --services 2>/dev/null | grep -qx elasticsearch; then
  echo "[es] elasticsearch 서비스가 실행 중이 아닙니다 — docker compose --profile search up -d elasticsearch (또는 make up) 후 다시 실행" >&2
  exit 2
fi

echo "[es] api · worker 를 .env 값으로 다시 만듦 (restart 는 환경변수를 바꾸지 않음)"
$COMPOSE up -d api worker >/dev/null

TMP_USER="nhdip_reset_$(openssl rand -hex 4)"
TMP_PW="$(openssl rand -hex 18)"
cleanup() { $COMPOSE exec -T elasticsearch bin/elasticsearch-users userdel "$TMP_USER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "[es] 임시 관리 계정 생성 (끝나면 지움)"
$COMPOSE exec -T elasticsearch bin/elasticsearch-users useradd "$TMP_USER" -p "$TMP_PW" -r superuser >/dev/null

echo "[es] elastic 비밀번호를 .env 의 ES_PASSWORD 로 맞추는 중 (최대 60초)"
$COMPOSE exec -T -e ES_RESET_USER="$TMP_USER" -e ES_RESET_PASSWORD="$TMP_PW" api python -m nhdip.cli es-password --timeout 60

cleanup
trap - EXIT

echo "[es] api · worker 다시 시작 (캐시된 연결 · 차단기 초기화)"
$COMPOSE restart api worker >/dev/null
for _ in $(seq 1 30); do
  $COMPOSE exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" >/dev/null 2>&1 && break
  sleep 2
done
echo "[es] 검색 점검 (색인 동기화는 워커가 1분 안에 이어서 함)"
$COMPOSE exec -T api python -m nhdip.cli kb-es --check || echo "[es] 연결은 됐고 색인 동기화가 남아 있을 수 있습니다 — 1~2분 뒤 관리자 [AI 어시스턴트 색인]에서 확인"
echo "[es] 완료"
