#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# [내부망 · kubectl 되는 곳] 비밀값 Secret 만들기 — .env · values 파일에 비밀값을 두지 않는다
#
#   NS=nhdip bash scripts/create-secrets.sh                 # 처음 1회: 무작위 비밀값으로 nhdip-secrets 생성(파일로 남기지 않음)
#   NS=nhdip bash scripts/create-secrets.sh add LLM_DEFAULT_API_KEY    # 값 추가 · 변경(화면에 보이지 않게 입력)
#   NS=nhdip bash scripts/create-secrets.sh add NC_SSO_VERIFIER_TOKEN --random
#   NS=nhdip bash scripts/create-secrets.sh keys            # 들어 있는 키 이름만 보기
#
# 처음 만들 때 외부에서 받은 값을 같이 넣으려면 같은 이름의 환경변수로 넘긴다(셸 기록에 남지 않게 read -s 로 받아 export):
#   LLM_DEFAULT_API_KEY · OIDC_CLIENT_SECRET · ALERT_SMTP_PASSWORD · ALERT_WEBHOOK_URL · BOOTSTRAP_ADMIN_PASSWORD
#
# 주의: POSTGRES_PASSWORD · NEO4J_PASSWORD · ES_PASSWORD 는 데이터가 처음 만들어질 때의 값으로 굳는다 — 설치 뒤 바꾸지 않는다.
#       CONFIG_ENC_KEY 를 바꾸면 화면에서 저장한 연결 키(LLM 등)를 풀 수 없다.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
NS="${NS:-nhdip}"
NAME="${SECRET_NAME:-nhdip-secrets}"
CMD="${1:-create}"
command -v kubectl >/dev/null || { echo "오류: kubectl 이 필요합니다" >&2; exit 1; }

if command -v openssl >/dev/null 2>&1; then
  rand_hex() { openssl rand -hex "$1"; }
  rand_b64() { openssl rand -base64 32 | tr -d '\n'; }
else
  rand_hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }
  rand_b64() { head -c 32 /dev/urandom | base64 | tr -d '\n'; }
fi
exists() { kubectl -n "$NS" get secret "$NAME" >/dev/null 2>&1; }

case "$CMD" in
  create)
    kubectl get namespace "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS"
    if exists; then
      echo "[secret] $NS/$NAME 가 이미 있습니다 — 다시 만들면 기존 DB 비밀번호와 맞지 않습니다. 값 추가 · 변경은: $0 add <키>" >&2
      exit 1
    fi
    lines=(
      "POSTGRES_PASSWORD=$(rand_hex 16)"
      "NEO4J_PASSWORD=$(rand_hex 16)"
      "APP_DB_PASSWORD=$(rand_hex 16)"
      "ES_PASSWORD=$(rand_hex 16)"
      "SESSION_SECRET=$(rand_hex 32)"
      "CONFIG_ENC_KEY=$(rand_b64)"
      "BOOTSTRAP_ADMIN_PASSWORD=${BOOTSTRAP_ADMIN_PASSWORD:-Nh!$(rand_hex 6)}"
      "NC_SSO_VERIFIER_TOKEN=$(rand_hex 24)"
      "LITELLM_MASTER_KEY=sk-$(rand_hex 24)"
      "LITELLM_UI_PASSWORD=$(rand_hex 12)"
    )
    for k in LLM_DEFAULT_API_KEY OIDC_CLIENT_SECRET ALERT_SMTP_PASSWORD ALERT_WEBHOOK_URL DEMO_USER_PASSWORD; do
      if [ -n "${!k:-}" ]; then lines+=("$k=${!k}"); fi
    done
    # 값은 프로세스 대체(<(...))로만 넘긴다 — 명령줄 인자 · 디스크에 남지 않는다
    kubectl -n "$NS" create secret generic "$NAME" --from-env-file=<(printf '%s\n' "${lines[@]}")
    kubectl -n "$NS" label secret "$NAME" app.kubernetes.io/part-of=nhdip >/dev/null
    echo "[secret] $NS/$NAME 생성 — 키 ${#lines[@]}개"
    echo "[secret] 최초 관리자 비밀번호 보기: kubectl -n $NS get secret $NAME -o jsonpath='{.data.BOOTSTRAP_ADMIN_PASSWORD}' | base64 -d; echo"
    ;;
  add)
    KEY="${2:?사용법: $0 add <키> [--random]}"
    exists || { echo "오류: $NS/$NAME 이 없습니다 — 먼저 $0 create" >&2; exit 1; }
    if [ "${3:-}" = "--random" ]; then
      VAL="$(rand_hex 24)"
    else
      read -rsp "$KEY 값(화면에 보이지 않음): " VAL; echo
      [ -n "$VAL" ] || { echo "빈 값은 넣지 않습니다" >&2; exit 1; }
    fi
    esc=${VAL//\\/\\\\}; esc=${esc//\"/\\\"}
    kubectl -n "$NS" patch secret "$NAME" --type merge --patch-file=<(printf '{"stringData":{"%s":"%s"}}' "$KEY" "$esc")
    echo "[secret] $KEY 저장 — 반영: kubectl -n $NS rollout restart deploy/api deploy/worker (SSO 토큰이면 deploy/sso-verifier 도)"
    ;;
  keys)
    kubectl -n "$NS" get secret "$NAME" -o go-template='{{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}'
    ;;
  *)
    echo "사용법: $0 [create | add <키> [--random] | keys]" >&2; exit 1 ;;
esac
