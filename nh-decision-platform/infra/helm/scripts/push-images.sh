#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# [내부망 · Nexus 에 접근되는 서버] 반입한 이미지 tar 를 Nexus 도커 저장소에 올린다
#
#   bash scripts/push-images.sh <Nexus 주소>                 # 예: nexus.example.local:5000  또는  nexus.example.local:5000/nhdip
#   TOOL=skopeo bash scripts/push-images.sh <Nexus 주소>     # 도커 데몬 없이(skopeo) — 인증: skopeo login <주소>
#
# 올라가는 이름 = <Nexus 주소>/<이미지 이름:태그>  (values-closed.yaml 의 global.imageRegistry 에 같은 주소를 적는다)
# 먼저 로그인: docker login <Nexus 호스트:포트>   (HTTP · 사설 인증서면 docker 의 insecure-registries · CA 설정)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
REGISTRY="${1:-${REGISTRY:-}}"
TOOL="${TOOL:-docker}"
[ -n "$REGISTRY" ] || { echo "사용법: bash scripts/push-images.sh <Nexus 주소>   예: nexus.example.local:5000" >&2; exit 1; }
REGISTRY="${REGISTRY%/}"
cd "$(dirname "$0")/.."
LIST=images/images.txt
[ -f "$LIST" ] || { echo "오류: $LIST 가 없습니다 — 묶음 폴더(nhdip-closed-<TAG>)에서 실행하세요" >&2; exit 1; }

if [ -f SHA256SUMS ]; then
  echo "[push] 체크섬 확인"
  if command -v sha256sum >/dev/null; then sha256sum -c --quiet SHA256SUMS; else shasum -a 256 -c --quiet SHA256SUMS; fi
fi

while read -r file ref; do
  [ -n "$file" ] || continue
  dst="$REGISTRY/$ref"
  echo "[push] $file → $dst"
  case "$TOOL" in
    docker | nerdctl)
      "$TOOL" load -i "images/$file" >/dev/null
      "$TOOL" tag "$ref" "$dst"
      "$TOOL" push "$dst"
      ;;
    skopeo)
      # 사설 인증서 · HTTP Nexus 면 SKOPEO_OPTS="--dest-tls-verify=false"
      # shellcheck disable=SC2086
      skopeo copy ${SKOPEO_OPTS:-} "docker-archive:images/$file:$ref" "docker://$dst"
      ;;
    *) echo "TOOL 은 docker · nerdctl · skopeo 중 하나" >&2; exit 1 ;;
  esac
done < "$LIST"

echo
echo "[push] 완료 — values-closed.yaml 의 global.imageRegistry: \"$REGISTRY\""
