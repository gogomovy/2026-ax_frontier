#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# [외부 · 인터넷 되는 PC/빌드 서버] 폐쇄망 반입 묶음 만들기
#   이미지 빌드 · 받기 → 이미지별 tar → 헬름 차트 tgz → 값 파일 · 가이드 · 내부용 스크립트 → 묶음 tar 1개
#
#   bash infra/helm/scripts/bundle.sh                 # 결과: dist/nhdip-closed-<TAG>.tar
#   TAG=1.0.1 bash infra/helm/scripts/bundle.sh       # 태그 지정(기본: Chart.yaml appVersion)
#   WITH_SSO=0 WITH_LITELLM=1 bash infra/helm/scripts/bundle.sh
#
# 필요: docker(BuildKit) · tar · sha256sum(또는 shasum) · helm(없으면 차트를 tar 로 묶는다)
# Windows 는 Git Bash 또는 WSL 에서 Docker Desktop 과 함께 실행한다. 비밀값은 이 묶음에 들어가지 않는다.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

CHART_DIR=infra/helm/nhdip
APP_VERSION=$(awk -F'"' '/^appVersion:/{print $2}' "$CHART_DIR/Chart.yaml")
CHART_VERSION=$(awk '/^version:/{print $2}' "$CHART_DIR/Chart.yaml")
TAG=${TAG:-$APP_VERSION}
PLATFORM=${PLATFORM:-linux/amd64}
WITH_SSO=${WITH_SSO:-1}
WITH_LITELLM=${WITH_LITELLM:-0}
DIST=${DIST:-dist}
NAME="nhdip-closed-${TAG}"
OUT="$DIST/$NAME"

# 외부 이미지 — docker-compose.yml 기본값과 같게 둔다(태그 + 다이제스트 고정). 바꿀 때는 같은 이름의 환경변수로
PG_IMAGE=${PG_IMAGE:-pgvector/pgvector:pg16@sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a}
NEO4J_IMAGE=${NEO4J_IMAGE:-neo4j:5.26-community@sha256:c7d25c0eeebfe125718d58b72ed5d663c85d0479047733845eb2237c67ce8069}
ES_IMAGE_BASE=${ES_IMAGE_BASE:-docker.elastic.co/elasticsearch/elasticsearch:9.5.4}
LITELLM_IMAGE=${LITELLM_IMAGE:-docker.litellm.ai/berriai/litellm:main-stable@sha256:625981c83410a3ea68eb0697590a57ec1d764d634514d54fa5db0591077ee839}

log() { printf '\n\033[1m[bundle] %s\033[0m\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "[bundle] 오류: $1 이 필요합니다" >&2; exit 1; }; }
need docker
need tar

rm -rf "$OUT"
mkdir -p "$OUT/images" "$OUT/chart" "$OUT/scripts"
: > "$OUT/images/images.txt"

# 이미지 1개 저장 — images.txt 에 "<tar 파일> <이미지 이름:태그>" 를 적는다(push-images.sh 가 읽는다)
save() {
  local ref="$1" file="$2"
  log "저장 $ref → images/$file"
  docker save -o "$OUT/images/$file" "$ref"
  echo "$file $ref" >> "$OUT/images/images.txt"
}

build() {
  local ref="$1" ctx="$2"; shift 2
  log "빌드 $ref ($PLATFORM)"
  docker build --platform "$PLATFORM" -t "$ref" "$@" "$ctx"
}

# 외부 이미지를 받아 다이제스트 없이 차트가 쓰는 이름:태그로 붙인다
pull_as() {
  local src="$1" dst="$2" id
  log "받기 $src → $dst"
  docker pull --platform "$PLATFORM" "$src"
  id=$(docker image inspect --format '{{.Id}}' "$src" 2>/dev/null || docker image inspect --format '{{.Id}}' "${src%%:*}@${src#*@}")
  docker tag "$id" "$dst"
}

# ── 자체 이미지 ────────────────────────────────────────────────
build "nhdip/api:$TAG" apps/api
# 웹은 백엔드 주소를 빌드 때 굳힌다 — 차트의 api 서비스 이름(api)과 같아야 한다
build "nhdip/web:$TAG" apps/web --build-arg API_INTERNAL_URL=http://api:8000
build "nhdip/elasticsearch:$TAG" infra/elasticsearch --build-arg "ES_IMAGE_BASE=$ES_IMAGE_BASE"
if [ "$WITH_SSO" = "1" ]; then build "nhdip/sso-verifier:$TAG" infra/sso-verifier; fi

save "nhdip/api:$TAG" nhdip-api.tar
save "nhdip/web:$TAG" nhdip-web.tar
save "nhdip/elasticsearch:$TAG" nhdip-elasticsearch.tar
if [ "$WITH_SSO" = "1" ]; then save "nhdip/sso-verifier:$TAG" nhdip-sso-verifier.tar; fi

# ── 외부 이미지 ────────────────────────────────────────────────
pull_as "$PG_IMAGE" pgvector/pgvector:pg16
pull_as "$NEO4J_IMAGE" neo4j:5.26-community
save pgvector/pgvector:pg16 pgvector-pg16.tar
save neo4j:5.26-community neo4j-5.26-community.tar
if [ "$WITH_LITELLM" = "1" ]; then
  pull_as "$LITELLM_IMAGE" berriai/litellm:main-stable
  save berriai/litellm:main-stable litellm-main-stable.tar
fi

# ── 헬름 차트 ──────────────────────────────────────────────────
if command -v helm >/dev/null 2>&1; then
  log "차트 묶기 (helm package · appVersion=$TAG)"
  helm lint "$CHART_DIR" >/dev/null
  helm package "$CHART_DIR" --app-version "$TAG" -d "$OUT/chart"
else
  log "helm 이 없어 차트 폴더를 tgz 로 묶습니다(helm install 에 그대로 쓸 수 있음)"
  tar -czf "$OUT/chart/nhdip-${CHART_VERSION}.tgz" -C infra/helm nhdip
  if [ "$TAG" != "$APP_VERSION" ]; then
    echo "[bundle] 주의: TAG($TAG) ≠ appVersion($APP_VERSION) — values-closed.yaml 에 global.imageTag: \"$TAG\" 를 적으세요"
  fi
fi

# ── 값 파일 · 가이드 · 내부용 스크립트 ───────────────────────────
cp infra/helm/values-closed.yaml "$OUT/"
cp "infra/helm/폐쇄망_헬름배포_가이드.md" "$OUT/"
cp infra/helm/scripts/push-images.sh infra/helm/scripts/create-secrets.sh "$OUT/scripts/"
chmod +x "$OUT/scripts/"*.sh
cat > "$OUT/VERSION" <<EOF
tag=$TAG
chart=$CHART_VERSION
platform=$PLATFORM
built=$(date '+%Y-%m-%d %H:%M:%S %z')
commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
EOF

# ── 무결성 · 묶음 ──────────────────────────────────────────────
log "체크섬"
if command -v sha256sum >/dev/null 2>&1; then SUM=(sha256sum); else SUM=(shasum -a 256); fi
( cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 "${SUM[@]}" > SHA256SUMS )
log "묶음 $DIST/$NAME.tar"
tar -cf "$DIST/$NAME.tar" -C "$DIST" "$NAME"
ls -lh "$DIST/$NAME.tar"
cat "$OUT/images/images.txt"
echo
echo "[bundle] 완료 — $DIST/$NAME.tar 를 반입하세요. 내부에서: tar -xf $NAME.tar && cd $NAME && 가이드 §3"
