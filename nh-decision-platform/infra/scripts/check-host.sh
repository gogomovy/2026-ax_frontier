#!/usr/bin/env bash
# 서버 점검 (B.34) — 처음 띄우기 전에: Docker · Compose · buildx 버전 · 메모리 · 디스크 · 포트 · .env
#   make host-check   (또는 bash infra/scripts/check-host.sh)
# 문제가 있으면 고치는 명령을 함께 보여 준다. 아무것도 바꾸지 않는다.
set -uo pipefail
cd "$(dirname "$0")/../.."
fail=0; warn=0
ok()   { printf 'OK    %s\n' "$1"; }
bad()  { printf 'FAIL  %s\n' "$1"; [ -n "${2:-}" ] && printf '      → %s\n' "$2"; fail=$((fail + 1)); }
note() { printf 'WARN  %s\n' "$1"; [ -n "${2:-}" ] && printf '      → %s\n' "$2"; warn=$((warn + 1)); }
ver_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }  # $1 >= $2

ARCH=$(uname -m); BX_ARCH=$([ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ] && echo arm64 || echo amd64)

# Docker
if ! command -v docker >/dev/null; then
  bad "docker 없음" "sudo dnf install -y docker && sudo systemctl enable --now docker && sudo usermod -aG docker \$USER && newgrp docker"
elif ! docker info >/dev/null 2>&1; then
  bad "docker 데몬에 접속할 수 없음(꺼져 있거나 권한 없음)" "sudo systemctl enable --now docker; 권한이면 sudo usermod -aG docker \$USER 후 다시 로그인"
else
  ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)"
fi

# Compose v2 플러그인
CV=$(docker compose version --short 2>/dev/null | sed 's/^v//')
if [ -z "$CV" ]; then
  bad "docker compose 플러그인 없음" "sudo mkdir -p /usr/local/lib/docker/cli-plugins && sudo curl -fSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m) -o /usr/local/lib/docker/cli-plugins/docker-compose && sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose"
elif ! ver_ge "$CV" "2.20.0"; then
  note "docker compose $CV — 2.20 이상 권장" "위 명령으로 최신 플러그인 설치"
else
  ok "docker compose $CV"
fi

# buildx (compose build 는 0.17 이상 필요)
BV=$(docker buildx version 2>/dev/null | awk '{print $2}' | sed 's/^v//' | sed 's/-.*//')
NEED_BX="0.17.0"
if [ -n "$CV" ] && ! ver_ge "$(echo "$CV" | sed 's/-.*//')" "2.30.0"; then NEED_BX="0.0.0"; fi  # compose 2.30 이상만 buildx 0.17 요구
if [ -z "$BV" ] || ! ver_ge "$BV" "$NEED_BX"; then
  bad "docker buildx ${BV:-없음} — compose build 는 0.17.0 이상 필요" "mkdir -p ~/.docker/cli-plugins && curl -fSL https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-${BX_ARCH} -o ~/.docker/cli-plugins/docker-buildx && chmod +x ~/.docker/cli-plugins/docker-buildx"
else
  ok "docker buildx $BV"
fi

# 메모리 · 디스크
if [ -r /proc/meminfo ]; then
  MEM=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
  SWAP=$(awk '/SwapTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
  if [ $((MEM + SWAP)) -lt 8 ]; then
    note "메모리 ${MEM}GB + 스왑 ${SWAP}GB — 빌드 중 메모리 부족(exit 137) 가능, 8GB 이상 권장" "sudo dd if=/dev/zero of=/swapfile bs=1M count=4096 && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile"
  else
    ok "메모리 ${MEM}GB + 스왑 ${SWAP}GB"
  fi
fi
DISK=$(df -Pk . | awk 'NR==2 {printf "%d", $4/1024/1024}')
if [ "${DISK:-0}" -lt 15 ]; then note "남은 디스크 ${DISK}GB — 이미지 · 볼륨에 15GB 이상 권장" "docker system prune -af (사용하지 않는 이미지 정리) 또는 볼륨 확장"; else ok "남은 디스크 ${DISK}GB"; fi

# .env
if [ ! -f .env ]; then
  note ".env 없음 — 처음이면 정상" "bash infra/scripts/ensure-env.sh (또는 make env)"
else
  DUP=$(grep -E '^[A-Z_][A-Z0-9_]*=' .env | cut -d= -f1 | sort | uniq -d | tr '\n' ' ')
  if [ -n "$DUP" ]; then
    bad ".env 에 같은 키가 여러 번: ${DUP}— 어느 값이 쓰일지 헷갈림" "bash infra/scripts/set-env.sh <키> <값> 으로 다시 지정(중복 줄을 하나로 정리)"
  else
    ok ".env 키 중복 없음"
  fi
  for k in SESSION_SECRET CONFIG_ENC_KEY POSTGRES_PASSWORD NEO4J_PASSWORD BOOTSTRAP_ADMIN_PASSWORD; do
    grep -qE "^${k}=.+" .env || bad ".env 의 ${k} 가 비어 있음" "bash infra/scripts/ensure-env.sh"
  done
fi

# 포트
WEB_PORT=$(grep -E '^WEB_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2); WEB_PORT=${WEB_PORT:-3000}
RUNNING=$(docker compose ps -q web 2>/dev/null)
if [ -z "$RUNNING" ] && command -v ss >/dev/null && ss -ltn "( sport = :${WEB_PORT} )" | grep -q LISTEN; then
  bad "웹 포트 ${WEB_PORT} 를 다른 프로그램이 쓰는 중" "sudo ss -ltnp | grep :${WEB_PORT} 로 확인 후 종료하거나 bash infra/scripts/set-env.sh WEB_PORT <다른 포트>"
else
  ok "웹 포트 ${WEB_PORT}"
fi
if [ "$WEB_PORT" -lt 1024 ] 2>/dev/null; then ok "1024 미만 포트(${WEB_PORT})는 Docker 가 대신 열어 root 권한 불필요"; fi

# 외부 접속 안내 (AWS)
TOKEN=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null)
if [ -n "$TOKEN" ]; then
  PUB=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)
  SG=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/security-groups 2>/dev/null | tr '\n' ' ')
  if [ -n "$PUB" ]; then
    ok "EC2 공인 IP ${PUB} · 보안 그룹 ${SG}— 외부 접속은 보안 그룹 인바운드 TCP ${WEB_PORT} 필요: http://${PUB}$([ "$WEB_PORT" = 80 ] || echo ":${WEB_PORT}")"
  else
    note "EC2 공인 IP 없음 — 외부에서 직접 접속할 수 없음" "SSH/SSM 터널(README '서버 배포') 또는 ALB 사용"
  fi
fi

echo
echo "실패 ${fail} · 확인 ${warn}"
[ "$fail" -eq 0 ]
