#!/usr/bin/env bash
# .env 준비 (DEP-03)
#  - .env 가 없으면 .env.example 을 복사한다.
#  - .env.example 에 있는데 .env 에 없는 키는 뒤에 추가한다(기존 값은 절대 덮어쓰지 않는다).
#  - 비어 있는 비밀값은 무작위로 채운다.
set -euo pipefail
cd "$(dirname "$0")/../.."

EXAMPLE=.env.example
TARGET=.env

[ -f "$TARGET" ] || { cp "$EXAMPLE" "$TARGET"; echo "[env] .env 생성"; }

# 1) 빠진 키 추가
added=0
while IFS= read -r line; do
  [[ "$line" =~ ^[A-Z_][A-Z0-9_]*= ]] || continue
  key="${line%%=*}"
  if ! grep -qE "^${key}=" "$TARGET"; then
    [ "$added" -eq 0 ] && printf '\n# ── make env 가 추가한 키 (%s) ──\n' "$(date +%F)" >> "$TARGET"
    echo "$line" >> "$TARGET"
    added=$((added + 1))
  fi
done < "$EXAMPLE"
[ "$added" -gt 0 ] && echo "[env] 누락 키 ${added}개 추가"

# 2) 비어 있는 비밀값 생성
rand_hex() { openssl rand -hex "$1"; }
rand_b64() { openssl rand -base64 32 | tr -d '\n'; }

fill() {
  local key="$1" value="$2"
  if grep -qE "^${key}=$" "$TARGET"; then
    # macOS / GNU sed 모두 호환되도록 임시 파일 사용
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k && $2=="" {print k"="v; next} {print}' "$TARGET" > "$TARGET.tmp"
    mv "$TARGET.tmp" "$TARGET"
    echo "[env] ${key} 생성"
  fi
}

fill POSTGRES_PASSWORD "$(rand_hex 16)"
fill NEO4J_PASSWORD "$(rand_hex 16)"
fill APP_DB_PASSWORD "$(rand_hex 16)"
fill SESSION_SECRET "$(rand_hex 32)"
fill CONFIG_ENC_KEY "$(rand_b64)"
fill LITELLM_MASTER_KEY "sk-$(rand_hex 24)"
fill LITELLM_UI_PASSWORD "$(rand_hex 12)"
fill BOOTSTRAP_ADMIN_PASSWORD "Nh!$(rand_hex 6)"
fill ES_PASSWORD "$(rand_hex 16)"

chmod 600 "$TARGET"
# 3) 같은 키가 여러 줄이면 경고 (echo >> 로 추가한 경우 — 값 지정은 infra/scripts/set-env.sh)
DUP=$(grep -E '^[A-Z_][A-Z0-9_]*=' "$TARGET" | cut -d= -f1 | sort | uniq -d | tr '\n' ' ')
[ -n "$DUP" ] && echo "[env] 경고: 같은 키가 여러 줄 — ${DUP}→ bash infra/scripts/set-env.sh <키> <값> 으로 한 줄로 정리하세요" >&2
echo "[env] 준비 완료 — 최초 관리자 사번: $(grep -E '^BOOTSTRAP_ADMIN_EMP_NO=' "$TARGET" | cut -d= -f2) (비밀번호는 .env 의 BOOTSTRAP_ADMIN_PASSWORD)"
