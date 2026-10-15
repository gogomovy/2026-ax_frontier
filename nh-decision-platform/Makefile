SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: upload-test help env build up down logs ps restart seed reset-data sample sample-verify reset test e2e eval perf web-dev api-sh admin-pass backup restore wait-idle a11y keyboard preflight host-check set es-password

help:
	@echo "── 전체 기동 (Docker) ─────────────────────────────────────"
	@echo "make up          - .env 준비 → 이미지 빌드 → 5개 서비스 기동 (최초 시드 자동)"
	@echo "make ps          - 상태 확인"
	@echo "make logs        - 전체 로그 (s=api 처럼 서비스 지정 가능)"
	@echo "make down        - 중지 (데이터 유지)"
	@echo "make reset       - 중지 + 볼륨 삭제 (초기 상태로)"
	@echo "make seed        - 기본 설정·데이터 정의 시드 재실행 (멱등 · 업무 수치는 넣지 않음)"
	@echo "make reset-data  - 업무 자료 비우기 미리보기(지울 행 수) — YES=1 이면 실제로 지움. 사용자 · 설정 · 데이터셋 정의는 남김"
	@echo "make sample      - 시연 자료 패키지(엑셀 · CSV · PDF)를 실제 업로드 API 로 올리기 (같은 파일은 건너뜀)"
	@echo "make sample-verify - 엑셀에서 독립 계산한 기대값 ↔ 화면 API 수치 대조"
	@echo "make test        - 백엔드 테스트 (api 컨테이너)"
	@echo "make e2e         - 브라우저 E2E (기동 중인 스택 대상, Node 20+ 필요)"
	@echo "make a11y        - 자동 접근성 점검(axe-core · WCAG 2.1 A·AA 자동 규칙, 기동 중인 스택 대상)"
	@echo "make keyboard    - 질문하기 패널 키보드 전용 점검(Tab · Enter · Esc 로 열기 · 질문 · 피드백 · 닫기, 기동 중인 스택 대상)"
	@echo "make eval        - 골든셋 평가 (기준값 대조 · 결과를 관리자 [골든셋 평가]에 게시)"
	@echo "make perf        - 성능 측정 (주요 API p50 · p95 · 기준치 대조)"
	@echo "make admin-pass  - 최초 관리자 사번·비밀번호 표시"
	@echo "make preflight   - 운영 준비 점검 (보안 · 계정 · LLM · 워커 · 알림 · 백업 — 위험 항목이 있으면 실패)"
	@echo "make host-check  - 서버 점검 (Docker · Compose · buildx 버전 · 메모리 · 디스크 · 포트) — 처음 띄우기 전에"
	@echo "make set k=WEB_PORT v=80 - .env 값 지정(같은 키 중복 없이) → make up 으로 반영"
	@echo "make backup      - DB(업무 · litellm) 덤프 + 업로드 파일 → backups/<시각>/"
	@echo "make restore FROM=backups/<시각> CONFIRM=yes - 백업에서 복구 (현재 데이터 덮어씀)"
	@echo "make wait-idle   - 이벤트 · 작업 처리가 끝날 때까지 대기"
	@echo "make es-password - Elasticsearch 401(인증 실패) 해결 — ES 볼륨의 elastic 비밀번호를 .env 의 ES_PASSWORD 로 맞춤 (데이터 유지)"
	@echo ""
	@echo "── 프론트만 (도커 없이 · 백엔드 API 필요) ─────────────────"
	@echo "make web-dev     - apps/web 개발 서버 (API_INTERNAL_URL 의 백엔드에 연결 · 기본 http://localhost:8000)"

env:
	@bash infra/scripts/ensure-env.sh

build: env
	$(COMPOSE) build

up: env
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  WEB      → http://localhost:$${WEB_PORT:-3000}   (로그인 화면)"
	@echo "  API      → http://localhost:$${API_PORT:-8000}/health   (문서 /docs 는 API_DOCS=true 일 때)"
	@echo "  LLM      → 관리자 [LLM 연동] 에서 외부 LiteLLM 주소 · 키 입력 (내장 게이트웨이는 COMPOSE_PROFILES=litellm)"
	@echo "  Neo4j    → http://localhost:$${NEO4J_HTTP_PORT:-7474}"
	@echo "  최초 관리자 계정: make admin-pass"

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=150 $(s)

restart:
	$(COMPOSE) restart $(s)

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

seed:
	$(COMPOSE) exec -e NHDIP_USE_APP_ROLE=0 api python -m nhdip.cli seed

# 업무 자료 비우기 (M.19 · Q203) — 올린 자료 · 계산 결과 · 화면 산출물 · 색인 · 그래프를 지우고 정의만 남김. 되돌릴 수 없으니 먼저 make backup
reset-data:
	$(COMPOSE) exec -T -e NHDIP_USE_APP_ROLE=0 api python -m nhdip.cli reset-data $(if $(YES),--yes,)

sample:
	$(COMPOSE) exec -T api python -m nhdip.sample upload --base-url http://localhost:8000

sample-verify:
	$(COMPOSE) exec -T api python -m nhdip.sample verify --base-url http://localhost:8000

test:
	$(COMPOSE) exec -e NHDIP_USE_APP_ROLE=0 api python -m pytest -q tests
e2e:
	cd apps/e2e && npm install --no-audit --no-fund >/dev/null && \
	set -a && . ../../.env && set +a && \
	E2E_ADMIN_EMP="$$BOOTSTRAP_ADMIN_EMP_NO" E2E_ADMIN_PW="$$BOOTSTRAP_ADMIN_PASSWORD" E2E_BASE="http://localhost:$${WEB_PORT:-3000}" node e2e.mjs

upload-test:
	@bash infra/scripts/upload-test.sh
a11y:
	cd apps/e2e && npm install --no-audit --no-fund >/dev/null && \
	set -a && . ../../.env && set +a && \
	E2E_ADMIN_EMP="$$BOOTSTRAP_ADMIN_EMP_NO" E2E_ADMIN_PW="$$BOOTSTRAP_ADMIN_PASSWORD" E2E_BASE="http://localhost:$${WEB_PORT:-3000}" node a11y.mjs
keyboard:
	cd apps/e2e && npm install --no-audit --no-fund >/dev/null && \
	set -a && . ../../.env && set +a && \
	E2E_ADMIN_EMP="$$BOOTSTRAP_ADMIN_EMP_NO" E2E_ADMIN_PW="$$BOOTSTRAP_ADMIN_PASSWORD" E2E_BASE="http://localhost:$${WEB_PORT:-3000}" node keyboard.mjs
eval:
	$(COMPOSE) exec api python -m nhdip.evals --publish
perf:
	$(COMPOSE) exec api python -m nhdip.perf
api-sh:
	$(COMPOSE) exec api bash

admin-pass:
	@grep -E '^BOOTSTRAP_ADMIN_(EMP_NO|PASSWORD)=' .env

# 화면 데이터는 항상 백엔드 API 에서 온다(목데이터 모드 없음) — API_INTERNAL_URL(기본 http://localhost:8000)의 api 가 떠 있어야 한다
web-dev:
	cd apps/web && npm install && npm run dev
backup:
	@bash infra/scripts/backup.sh
restore:
	@bash infra/scripts/restore.sh
preflight:
	$(COMPOSE) exec -T api python -m nhdip.cli preflight
host-check:
	@bash infra/scripts/check-host.sh
set:
	@bash infra/scripts/set-env.sh "$(k)" "$(v)"
wait-idle:
	$(COMPOSE) exec -T api python -m nhdip.cli wait-idle --timeout $${t:-300}
# Elasticsearch 인증 실패(HTTP 401) — ES 는 ELASTIC_PASSWORD 를 볼륨을 처음 만들 때만 쓴다. .env 와 다르면 맞춘다 (Phase K · ES-02)
es-password: env
	@bash infra/scripts/es-sync-password.sh
