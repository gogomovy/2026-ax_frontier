#!/usr/bin/env bash
# .env 값 지정 (B.34) — 같은 키의 기존 줄을 모두 지우고 한 줄로 쓴다(echo >> 로 추가하면 키가 겹친다).
#   bash infra/scripts/set-env.sh WEB_PORT 80
#   make set k=WEB_PORT v=80
# 값을 바꾼 뒤에는 make up(또는 docker compose up -d)으로 반영한다.
set -euo pipefail
cd "$(dirname "$0")/../.."
KEY="${1:?키가 필요합니다 (예: WEB_PORT)}"
VAL="${2-}"
[[ "$KEY" =~ ^[A-Z_][A-Z0-9_]*$ ]] || { echo "키 형식 오류: $KEY (대문자 · 숫자 · _)" >&2; exit 2; }
[ -f .env ] || bash infra/scripts/ensure-env.sh >/dev/null
TMP=$(mktemp)
grep -vE "^${KEY}=" .env > "$TMP" || true
printf '%s=%s\n' "$KEY" "$VAL" >> "$TMP"
cat "$TMP" > .env && rm -f "$TMP"
chmod 600 .env
case "$KEY" in
  *SECRET*|*PASSWORD*|*KEY*|*TOKEN*) echo "[env] ${KEY} 설정(값 숨김)";;
  *) echo "[env] ${KEY}=${VAL}";;
esac
echo "[env] 반영: make up  (또는 docker compose up -d)"
