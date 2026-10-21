#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# [내부망] 반입한 이미지 tar 를 Harbor 에 올리는 도우미 — 직접 올려도 된다(가이드 §3)
#
#   bash scripts/push-images.sh <Harbor 주소>/<프로젝트>              # 예: 16.24.113.77/nhnavi
#   TOOL=skopeo bash scripts/push-images.sh <Harbor 주소>/<프로젝트>  # 도커 데몬 없이(skopeo) — 인증: skopeo login <Harbor 주소>
#
# 올라가는 이름 = <Harbor 주소>/<프로젝트>/<원래 이름:태그>   예: 16.24.113.77/nhnavi/nhdip/api:1.0.0
# 끝나면 values-closed.yaml 의 global.imageRegistry 에 <Harbor 주소>/<프로젝트> 만 적으면 된다(images.* 는 그대로)
#
# 먼저: Harbor 화면에서 프로젝트를 만들고(push 권한), docker login <Harbor 주소>
#       Harbor 가 HTTP 이거나 사설 인증서면 이 PC 도커의 /etc/docker/daemon.json "insecure-registries" 에 Harbor 주소를 넣고 도커 재시작
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
REGISTRY="${1:-${REGISTRY:-}}"
TOOL="${TOOL:-docker}"
[ -n "$REGISTRY" ] || { echo "사용법: bash scripts/push-images.sh <Harbor 주소>/<프로젝트>   예: 16.24.113.77/nhnavi" >&2; exit 1; }
REGISTRY="${REGISTRY%/}"
case "$REGISTRY" in
  */*) ;;
  *) echo "오류: Harbor 는 프로젝트가 필요합니다 — <Harbor 주소>/<프로젝트> 로 적으세요 (예: $REGISTRY/nhnavi)" >&2; exit 1 ;;
esac
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
    docker | nerdctl | podman)
      "$TOOL" load -i "images/$file" >/dev/null
      "$TOOL" tag "$ref" "$dst"
      "$TOOL" push "$dst"
      ;;
    skopeo)
      # HTTP · 사설 인증서 Harbor 면 SKOPEO_OPTS="--dest-tls-verify=false"
      # shellcheck disable=SC2086
      skopeo copy ${SKOPEO_OPTS:-} "docker-archive:images/$file:$ref" "docker://$dst"
      ;;
    *) echo "TOOL 은 docker · nerdctl · podman · skopeo 중 하나" >&2; exit 1 ;;
  esac
done < "$LIST"

echo
echo "[push] 완료 — values-closed.yaml 에 아래 한 줄을 적으세요 (images.* 는 그대로)"
echo "  global:"
echo "    imageRegistry: \"$REGISTRY\""
echo
echo "올라간 이미지:"
while read -r _ ref; do if [ -n "$ref" ]; then echo "  $REGISTRY/$ref"; fi; done < "$LIST"
