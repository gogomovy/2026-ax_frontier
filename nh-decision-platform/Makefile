SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: help env build up down logs ps restart seed reset test e2e eval perf web-dev api-sh admin-pass backup restore wait-idle a11y preflight host-check set

help:
	@echo "── 전체 기동 (Docker) ─────────────────────────────────────"
	@echo "make up          - .env 준비 → 이미지 빌드 → 5개 서비스 기동 (최초 시드 자동)"
	@echo "make ps          - 상태 확인"
	@echo "make logs        - 전체 로그 (s=api 처럼 서비스 지정 가능)"
	@echo "make down        - 중지 (데이터 유지)"
	@echo "make reset       - 중지 + 볼륨 삭제 (초기 상태로)"
	@echo "make seed        - 기본 설정·목데이터 시드 재실행 (멱등)"
	@echo "make test        - 백엔드 테스트 (api 컨테이너)"
	@echo "make e2e         - 브라우저 E2E (기동 중인 스택 대상, Node 20+ 필요)"
	@echo "make a11y        - 자동 접근성 점검(axe-core · WCAG 2.1 A·AA 자동 규칙, 기동 중인 스택 대상)"
	@echo "make eval        - 골든셋 평가 (기준값 대조 · 결과를 관리자 [골든셋 평가]에 게시)"
	@echo "make perf        - 성능 측정 (주요 API p50 · p95 · 기준치 대조)"
	@echo "make admin-pass  - 최초 관리자 사번·비밀번호 표시"
	@echo "make preflight   - 운영 준비 점검 (보안 · 계정 · LLM · 워커 · 알림 · 백업 — 위험 항목이 있으면 실패)"
	@echo "make host-check  - 서버 점검 (Docker · Compose · buildx 버전 · 메모리 · 디스크 · 포트) — 처음 띄우기 전에"
	@echo "make set k=WEB_PORT v=80 - .env 값 지정(같은 키 중복 없이) → make up 으로 반영"
	@echo "make backup      - DB(업무 · litellm) 덤프 + 업로드 파일 → backups/<시각>/"
	@echo "make restore FROM=backups/<시각> CONFIRM=yes - 백업에서 복구 (현재 데이터 덮어씀)"
	@echo "make wait-idle   - 이벤트 · 작업 처리가 끝날 때까지 대기"
	@echo ""
	@echo "── 프론트만 (도커 없이, 목데이터) ─────────────────────────"
	@echo "make web-dev     - apps/web 개발 서버"

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

test:
	$(COMPOSE) exec -e NHDIP_USE_APP_ROLE=0 api python -m pytest -q tests
e2e:
	cd apps/e2e && npm install --no-audit --no-fund >/dev/null && \
	set -a && . ../../.env && set +a && \
	E2E_ADMIN_EMP="$$BOOTSTRAP_ADMIN_EMP_NO" E2E_ADMIN_PW="$$BOOTSTRAP_ADMIN_PASSWORD" E2E_BASE="http://localhost:$${WEB_PORT:-3000}" node e2e.mjs

a11y:
	cd apps/e2e && npm install --no-audit --no-fund >/dev/null && \
	set -a && . ../../.env && set +a && \
	E2E_ADMIN_EMP="$$BOOTSTRAP_ADMIN_EMP_NO" E2E_ADMIN_PW="$$BOOTSTRAP_ADMIN_PASSWORD" E2E_BASE="http://localhost:$${WEB_PORT:-3000}" node a11y.mjs
eval:
	$(COMPOSE) exec api python -m nhdip.evals --publish
perf:
	$(COMPOSE) exec api python -m nhdip.perf
api-sh:
	$(COMPOSE) exec api bash

admin-pass:
	@grep -E '^BOOTSTRAP_ADMIN_(EMP_NO|PASSWORD)=' .env

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
