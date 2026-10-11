# 2026 AX 프런티어

이 브랜치(`feat/nh-decision-platform`)에는 **NH AI 경영 의사결정 플랫폼**이 `nh-decision-platform/` 폴더로 들어 있습니다.
기존 `main` 의 파일(`apps/`, `aidlc-docs/`, 정의서 문서 등)은 그대로 두었고, 플랫폼은 그 폴더 안에서 독립적으로 빌드 · 기동됩니다.

```
2026-ax_frontier/
├─ apps/ · aidlc-docs/ · *.md      # main 의 기존 내용 (변경 없음)
└─ nh-decision-platform/           # ← 이 문서가 설명하는 플랫폼
   ├─ apps/web        Next.js 16 · React 19 (로그인 · 업무 화면 · 관리자)
   ├─ apps/api        FastAPI + 워커 (인증 · 계산 커널 · 적재 · 워크플로우 · 검색)
   ├─ apps/e2e        브라우저 E2E (puppeteer)
   ├─ infra/          postgres init · litellm 설정 · 스크립트(.env 생성 등)
   ├─ .kiro/specs/    요구사항 · 설계 · 작업 목록
   ├─ docs/           작업 정리 · 성능 기준치 · 화면 캡처
   ├─ docker-compose.yml · Makefile · .env.example
   └─ README.md       플랫폼 상세 설명 (데이터 흐름 · 화면 · 구조 · 보안)
```

> 시나리오 · 원천 데이터(`data/` 폴더: 컬럼 정의서 엑셀, 활용데이터 등)는 저장소에 포함하지 않습니다.
> 플랫폼은 코드에 들어 있는 **목데이터(시뮬레이션 버전)** 로 시드되어 그 폴더 없이도 모든 화면이 동작합니다. 실데이터는 기동 후 관리자 화면에서 올립니다(아래 7장).

---

## 1. 사전 준비

| 항목 | 버전 · 조건 | 확인 명령 |
|---|---|---|
| Docker Desktop (또는 Docker Engine + Compose 플러그인) | Compose v2 (`docker compose`) | `docker compose version` |
| Docker 메모리 할당 | 최소 4GB, **권장 6~8GB** (5개 서비스 실사용 약 1.5GB, 빌드 시 더 필요) | Docker Desktop → Settings → Resources |
| 디스크 여유 | 약 5GB (이미지 약 3.5GB + 볼륨) | |
| git · make · openssl · bash | macOS / Linux 기본 포함 | `make -v`, `openssl version` |
| Node.js (선택) | 20 이상 — `make e2e`, `make web-dev` 에만 필요 | `node -v` |
| 인터넷 | 최초 빌드 시 이미지 · pip · npm 패키지 다운로드 | |

- Apple Silicon(arm64) · Intel(amd64) 모두 동작합니다(arm64 Mac 에서 검증).
- Windows 는 **WSL2(Ubuntu)** 안에서 아래 명령을 그대로 실행하세요. PowerShell 만 쓸 경우 2.3의 `make` 없이 실행하는 방법을 참고합니다.
- 사용하는 호스트 포트: `3000`(web) · `8000`(api) · `7474` · `7687`(neo4j). LLM 은 외부 LiteLLM 을 씁니다(서버에서 그 주소로 나갈 수 있어야 함). 이미 쓰고 있으면 4장에서 바꿉니다.

---

## 2. 처음 띄우기

### 2.1 코드 받기

```bash
git clone -b feat/nh-decision-platform https://github.com/gogomovy/2026-ax_frontier.git
cd 2026-ax_frontier/nh-decision-platform
```

이후 명령은 모두 `nh-decision-platform/` 폴더에서 실행합니다.

### 2.2 기동

```bash
make up
```

`make up` 이 하는 일:

1. **`.env` 준비** (`infra/scripts/ensure-env.sh`) — `.env` 가 없으면 `.env.example` 을 복사하고, 비어 있는 비밀값(DB · Neo4j 비밀번호, 세션 서명 키, 설정 암호화 키, LiteLLM 마스터 키, 최초 관리자 비밀번호)을 무작위로 채웁니다. 이미 있는 값은 덮어쓰지 않습니다.
2. **이미지 빌드** — `nhdip/api`(Python 3.12), `nhdip/web`(Node 20, Next standalone). 처음에는 네트워크에 따라 수 분~십여 분 걸립니다.
3. **5개 서비스 기동** — postgres → neo4j → api → worker · web 순서로 헬스체크를 기다리며 올라옵니다. (내장 LiteLLM 은 기본으로 띄우지 않습니다 — 필요하면 `.env` 에 `COMPOSE_PROFILES=litellm`)
4. **최초 1회 자동 초기화** — api 컨테이너가 DB 마이그레이션(alembic) → 기본 설정 · 목데이터 시드 → 최초 계산까지 수행합니다(멱등이라 재기동해도 중복되지 않음).

### 2.3 `make` 없이 실행 (Windows PowerShell 등)

```bash
bash infra/scripts/ensure-env.sh      # .env 생성 (bash · openssl 필요 — Git Bash 가능)
docker compose up -d --build
```

bash 를 쓸 수 없으면 `.env.example` 을 `.env` 로 복사한 뒤 비어 있는 `POSTGRES_PASSWORD` · `NEO4J_PASSWORD` · `SESSION_SECRET`(32바이트 이상 무작위) · `CONFIG_ENC_KEY`(base64 32바이트) · `LITELLM_MASTER_KEY`(`sk-` 로 시작) · `LITELLM_UI_PASSWORD` · `BOOTSTRAP_ADMIN_PASSWORD` 를 직접 채우고 `docker compose up -d --build` 를 실행합니다.

### 2.4 기동 확인

```bash
make ps                     # 5개 서비스(api · web · worker · postgres · neo4j) 가 (healthy)
make logs s=api             # api 로그 — "alembic upgrade head" → "seeding" → uvicorn 시작이 보이면 정상
curl -fsS http://localhost:8000/health
```

LLM 연결 상태와 관계없이 플랫폼 화면은 동작합니다(LLM 이 없으면 서술 문장만 기본 문장).

### 2.5 로그인

```bash
make admin-pass
# BOOTSTRAP_ADMIN_EMP_NO=00000001
# BOOTSTRAP_ADMIN_PASSWORD=Nh!xxxxxxxxxxxx   ← 각자 .env 에서 생성된 값
```

브라우저에서 http://localhost:3000 → 로그인 화면에 사번 `00000001` 과 위 비밀번호를 입력합니다.
비밀번호는 PC 마다 다르게 생성되며 `.env` 에만 있습니다(`.env` 는 커밋되지 않음).

---

## 3. 접속 주소

| 서비스 | 주소 | 용도 |
|---|---|---|
| web | http://localhost:3000 | 로그인 · 업무 화면 · 관리자(`/admin`) |
| api | http://localhost:8000/health | API 상태 확인 (API 문서 `/docs` 는 `.env` 에 `API_DOCS=true` 일 때) |
| neo4j | http://localhost:7474 | 온톨로지 그래프 브라우저 (사용자 `neo4j` / `.env` 의 `NEO4J_PASSWORD`) |
| (LLM) | 외부 LiteLLM | 관리자 `/admin/llm` 의 **간단 설정** 에서 주소 · 키 · 모델 입력 |

주요 업무 화면:

| 부서 | 경로 |
|---|---|
| 종합기획부 | `/hq/overview` 현황 · 목표 → `/hq/analysis` 데이터 분석 → `/hq/goals` 경영목표 설정 |
| 신용리스크관리부 | `/risk` 현황 → `/risk/analysis/[tabKey]` 분석 결과 → `/risk/guides` 수행방안 |
| 영업점 | `/branch` 현황(업적평가 득점 · 기준 변경 알림 · 사업부문) → `/branch/analysis/prime-corp` · `/branch/analysis/seomin` 영업 가이드 보고서 · 참고 `/branch/targets` (수원영통지점 001068 시뮬레이션 — 실데이터 · 세부기준 원본은 추후 반영) |
| 공통 | `/knowledge` 문서 · 데이터셋 · 용어집 |
| 관리자 | `/admin` — 사용자 승인, 화면 권한, 데이터셋 · 문서 업로드, 지표 · 규칙 · 워크플로우, LLM 연결, 모니터링, 에이전트 결정(`/admin/monitor/agents`) |

---

워크플로우 안에서는 변화 감지(LLM 중요도 판단) → 화면 갱신 → 실행 계획(LLM: 서술 대상 · 검색어 · 후속 워크플로우) → 근거 검색 · 서술(LLM) → 검증 순서로 에이전트가 동작하고, 이벤트마다 오케스트레이터(LLM)가 영향받는 워크플로우를 추가하며 실행 순서는 규칙으로 보장합니다. LLM 키가 없거나 판단이 실패하면 규칙으로 대신 판단합니다. 각 에이전트의 결정 · 판단 주체 · 근거는 관리자 [에이전트 결정]에서 볼 수 있습니다.

시연용 영업점 계정: `.env` 에 `DEMO_USER_PASSWORD` 를 넣고 처음 기동하면 `20250003`(수원영통지점) 으로 영업점 화면을 볼 수 있습니다. 관리자 계정으로도 모든 영업점 화면을 볼 수 있습니다.

## 4. 설정 바꾸기 (`.env`)

`.env` 를 고친 뒤 `make up` 을 다시 실행하면 바뀐 서비스만 재생성됩니다.

| 하고 싶은 것 | 키 |
|---|---|
| 포트 충돌 회피 | `WEB_PORT` · `API_PORT` · `LITELLM_PORT` · `NEO4J_HTTP_PORT` · `NEO4J_BOLT_PORT` |
| 시연용 부서 계정 만들기 | `DEMO_USER_PASSWORD=<비밀번호>` → 재기동 시 `20250001`(종합기획부) · `20250002`(신용리스크관리부) · `20250003`(영업점) 생성 |
| LLM 기본 연결 | `LLM_DEFAULT_BASE_URL` · `LLM_DEFAULT_API_KEY` · `LLM_DEFAULT_MODEL` (최초 시드 때만 반영 — 이후에는 관리자 `/admin/llm` 에서 변경) |
| HTTPS 뒤에서 운영 | `COOKIE_SECURE=1` |
| SSO(OIDC) | `OIDC_ISSUER` · `OIDC_CLIENT_ID` · `OIDC_CLIENT_SECRET` · `OIDC_REDIRECT_URI` |
| 운영 알림 채널 | `ALERT_WEBHOOK_URL` 또는 `ALERT_SMTP_*` |
| 다른 PC 에서 api · neo4j 접속 | `ADMIN_BIND=0.0.0.0` (기본은 이 PC 에서만) |
| 다른 주소(도메인 · 프록시)로 서비스 | `TRUSTED_ORIGINS=https://<웹 주소>` (변경 요청은 같은 출처만 허용) |
| API 문서 보기 | `API_DOCS=true` |

각 키의 설명은 `.env.example` 주석에 있습니다.

---

## 5. 처음 사용 순서

1. **LLM 연결(선택)** — 관리자 `/admin/llm` → **LiteLLM 연결 (간단 설정)** 에 외부(사내) LiteLLM 의 주소 · API 키 · 모델을 넣고 [저장하고 연결 확인]을 누릅니다. 확인되면 그 게이트웨이의 모델 목록이 나오니 눌러서 고르면 됩니다(재기동 불필요). 연결하지 않아도 모든 수치 · 표 · 차트는 계산 커널로 동작하고, 서술 문장만 기본 문장으로 대체됩니다.
2. **사용자 가입 · 승인** — 사용자는 `/signup` 에서 사번 8자리 + 소속으로 가입하고, 관리자가 `/admin/users` 에서 승인합니다.
3. **화면 권한** — `/admin/screens` 에서 조직 단위로 부여합니다(하위 조직 상속).
4. **데이터 반영** — 7장 참고.

---

## 6. 중지 · 재시작 · 초기화

```bash
make down          # 중지 (DB · 그래프 · 업로드 파일 볼륨 유지)
make up            # 다시 기동 (코드가 바뀌었으면 다시 빌드)
make restart s=api # 특정 서비스만 재시작
make reset         # 중지 + 볼륨 삭제 → 다음 make up 에서 처음 상태로 재시드
make seed          # 기본 설정 · 목데이터 시드만 다시 실행 (멱등)
make backup        # DB + 업로드 파일 → nh-decision-platform/backups/<시각>/
make restore FROM=backups/<시각> CONFIRM=yes   # 백업에서 복구 (현재 데이터를 덮어씀)
```
복구 후에는 관리자 [온톨로지]에서 재투영하면 그래프가 다시 만들어집니다.

`make reset` 은 업로드한 데이터 · 승인한 사용자 · 관리자 화면에서 바꾼 설정을 모두 지웁니다. `.env` 는 남으므로 관리자 비밀번호는 그대로입니다.

최신 코드 받기:

```bash
git pull
make up
```

---

## 7. 데이터 반영

- 기본 상태는 목데이터(시뮬레이션 버전)이며, 화면에 `시뮬레이션 데이터` 배지로 구분됩니다. 분석 기준일은 `2026-08-31`(`AS_OF_DEFAULT`).
- 실데이터: `/admin/datasets` 에서 데이터셋별로 업로드(당행 / 외부 구분) → 품질 검증 → 확정하면 관련 워크플로우만 다시 계산됩니다. 원천 엑셀 보고서(2633 · 2020 · 7790 형식)는 자동 인식합니다.
- 컬럼 정의서: 종합기획부 · 사업부서 · 영업점 컬럼 정의서 엑셀을 `/admin/contracts` 에 올리면 화면 컬럼과 계산 지표 · 행 생성기 · 원천을 연결하고 정의서 기대값과 계산값을 대조합니다(부서마다 `mart.hq_t01` · `mart.risk_t02` · `mart.branch_t03` 처럼 적재). 시드에 세 정의서가 이미 들어 있습니다.
- 흐름 보기: 관리자 `/admin/pipeline` 에서 원천 → 워크플로우 → 산출물 → 화면 연결과 노드별 실행 상태 · 담당 에이전트(LLM 모델 / 규칙) · 판단 타임라인을 한눈에 봅니다.
- 문서(규정 · 보고서 PDF/HWP 등): `/admin/datasets` 화면의 문서 영역에서 업로드하면 근거 검색과 온톨로지에 반영됩니다. DRM 이 걸린 파일은 업로드 단계에서 거부되므로 해제본을 올려야 합니다.

원본 데이터 파일은 저장소에 올리지 말고 각자 보관한 뒤 위 화면으로 반영합니다. `nh-decision-platform/.gitignore` 와 루트 `.gitignore` 모두 `data/` 를 제외합니다.

---

## 8. 검증 명령

| 명령 | 내용 |
|---|---|
| `make test` | 백엔드 단위 · 통합 테스트 (api 컨테이너 안에서 pytest) |
| `make e2e` | 브라우저 E2E — 기동 중인 스택 대상, 로그인 → 업무 화면 → 관리자 화면 점검 (Node 20+) |
| `make eval` | 골든셋 평가 — 기준값 · 판정 · 서술 출처 · 검색 · 질의 결과를 관리자 [골든셋 평가]에 게시 |
| `make perf` | 주요 API p50 · p95 측정 후 기준치(`perf_budgets.json`)와 대조 |
| `make wait-idle` | 이벤트 · 작업 처리가 끝날 때까지 대기 (기동 직후 선계산 확인) |
| `make a11y` | 자동 접근성 점검(axe-core, 주요 26개 화면) |
| `make upload-test` | 업로드 기반 에이전트 시험 — 별도 스택(포트 3100)을 새로 띄워 2026.09 시험 엑셀 · PDF 를 올리고 워크플로우 · 에이전트 판단 · 서술 · mart 갱신을 확인한 뒤 내림. LLM 을 쓰려면 `E2E_LLM_BASE` · `E2E_LLM_KEY` · `E2E_LLM_MODEL` 환경변수(키는 파일에 남지 않음) |

---

## 9. 프론트만 실행 (Docker 없이)

```bash
make web-dev       # = cd apps/web && npm install && npm run dev
```

http://localhost:3000 — 백엔드 없이 내장 목데이터로 화면만 띄웁니다(로그인 없이 페르소나 전환). 화면 디자인 확인용입니다.

---

## 10. 문제 해결

| 증상 | 확인 · 조치 |
|---|---|
| `port is already allocated` | 해당 포트를 쓰는 프로세스를 종료하거나 `.env` 의 `*_PORT` 를 바꾸고 `make up` |
| `SESSION_SECRET 가 .env 에 필요합니다` | `.env` 가 없거나 비밀값이 비어 있음 → `make env` 후 `make up` |
| api 가 계속 `unhealthy` | `make logs s=api` — DB 대기 · 마이그레이션 오류 확인. 볼륨이 예전 버전이면 `make reset` 후 `make up` |
| 빌드 중 메모리 부족으로 종료(exit 137) | Docker 메모리 할당을 6GB 이상으로 늘린 뒤 재시도 |
| 로그인이 안 됨 | `make admin-pass` 값 확인. 5회 실패 시 잠기고 30분 뒤 자동 해제됩니다. 바로 풀려면 다른 관리자가 `/admin/users` 에서 [잠금 해제]하거나, 관리자가 하나뿐이면 아래 명령으로 해제 |
| `요청이 너무 많습니다` (429) | 로그인 · 질의 속도 제한 — 안내된 초만큼 기다린 뒤 다시 시도 (기준은 관리자 설정 `auth.rate_limits`) |
| `허용되지 않은 출처의 요청입니다` (403) | 웹 주소가 다르게 보이는 프록시 환경 → `.env` 에 `TRUSTED_ORIGINS=<웹 주소>` 후 `make up` |
| `.env` 의 관리자 비밀번호를 바꿨는데 반영 안 됨 | 최초 관리자는 처음 시드 때만 만들어짐 → `/admin/users` 의 비밀번호 재설정을 쓰거나 `make reset` |
| 화면 숫자가 비어 있음 | worker 가 최초 계산 중일 수 있음 → `make logs s=worker`, 관리자 `/admin/monitor/flow` 에서 진행 확인 |
| 서술 문장이 기본 문장으로 나옴 | LLM 미연결 상태(정상 동작) → 5장 1번 |
| 사내망 · 프록시 환경에서 빌드 실패 | Docker Desktop 프록시 설정, 또는 pip · npm 미러를 지정한 뒤 재빌드 |

관리자 계정 잠금 해제(관리자가 하나뿐일 때, `.env` 의 `POSTGRES_USER` · `POSTGRES_DB` 를 바꿨다면 그 값으로):

```bash
docker compose exec postgres psql -U nhdip -d nhdip \
  -c "update iam.app_user set status='active', failed_count=0 where emp_no='00000001'"
```

오류 문의 시 브라우저 응답 헤더의 `X-Trace-Id` 를 관리자 [요청 추적](`/admin/monitor/trace`)에 넣으면 요청 → 워커 → DB 구간을 볼 수 있습니다.

---

## 11. 보안 메모

- 기본 비밀번호는 없습니다. 모든 비밀값은 PC 마다 `.env` 에 무작위로 생성되며 `.env` 는 커밋하지 않습니다.
- api(8000) · neo4j(7474/7687) 포트는 기본으로 이 PC(127.0.0.1)에서만 열립니다. web(3000)만 외부에 노출됩니다.
- 운영 모드에서는 기본 · 짧은 세션 키로 기동하지 않고, API 문서는 꺼져 있습니다. 보안 헤더(CSP 등) · CSRF 출처 검사 · 로그인 속도 제한이 기본으로 켜져 있습니다.
- api 는 데이터 조작만 가능한 DB 계정(`nhdip_app`)으로 접속해 감사 로그를 고치거나 지울 수 없습니다(`.env` 의 `APP_DB_PASSWORD`, make env 가 생성).
- 앞에 사내 프록시가 있으면 `.env` 의 `TRUSTED_PROXIES` 에 그 대역을 더해야 로그인 속도 제한 · 감사 기록이 실제 사용자 IP 기준이 됩니다.
- 적재 데이터에 주민등록번호 · 휴대전화 · 이메일 · 카드번호 형식 값이 있으면 적재를 거부하고, 차주명은 화면에서 가립니다(관리자 설정 `privacy.policy`).
- 로그인 후 `/admin/users` 에서 관리자 비밀번호를 재설정하고, 공유 환경에서는 `DEMO_USER_PASSWORD` 를 비워 두세요.

## 12. 서버 배포 (아마존 리눅스 2023 · EC2)
권장 사양: 메모리 8GB 이상(t3.large · 부족하면 스왑 4GB), 디스크 30GB 이상, x86 · Graviton 모두 가능. 이미지 · 패키지를 받기 위해 서버에서 인터넷으로 나가는 연결이 필요합니다.

```bash
# 1) 도구 — docker · git · make (설치 후 다시 로그인하거나 newgrp docker)
sudo dnf install -y docker git make openssl && sudo systemctl enable --now docker && sudo usermod -aG docker $USER && newgrp docker

# 2) compose · buildx 플러그인 (아마존 리눅스 저장소에는 없음 — compose 2.30 이상은 buildx 0.17 이상 필요)
ARCH=$(uname -m); BX=$([ "$ARCH" = aarch64 ] && echo arm64 || echo amd64)
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -fSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$ARCH -o /usr/local/lib/docker/cli-plugins/docker-compose
mkdir -p ~/.docker/cli-plugins && curl -fSL https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-$BX -o ~/.docker/cli-plugins/docker-buildx
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose; chmod +x ~/.docker/cli-plugins/docker-buildx

# 3) 코드 받기 → 플랫폼 폴더로 (gogomovy 저장소는 nh-decision-platform/ 안)
git clone -b feat/nh-decision-platform https://github.com/gogomovy/2026-ax_frontier.git && cd 2026-ax_frontier/nh-decision-platform

# 4) 점검 → 기동
make host-check       # Docker · buildx 버전 · 메모리 · 디스크 · .env · 포트 · EC2 공인 IP — FAIL 이 있으면 안내된 명령 실행
make up               # .env 비밀값 생성 → 빌드(처음 10~20분) → 기동
make wait-idle && make ps      # 5개 모두 (healthy)
make admin-pass       # 최초 관리자 사번 · 비밀번호
make preflight        # 운영 준비 점검 (관리자 [시스템 상태] 에도 표시)
```

**외부 접속**
- 웹만 외부에 열립니다(api · Neo4j 는 서버 안에서만). 서버에서 외부 LiteLLM 주소로 나갈 수 있어야 합니다. 80 포트로 열려면 `make set k=WEB_PORT v=80 && make up` 후 EC2 보안 그룹 인바운드에 `TCP 80` 을 추가하고 `http://<공인 IP>` 로 접속합니다.
- `.env` 값은 `make set k=<키> v=<값>` 으로 바꿉니다. `echo ... >> .env` 로 추가하면 같은 키가 두 줄이 되어 어느 값이 쓰일지 알 수 없습니다(`make host-check` 가 찾아 줍니다).
- 서버 안에서는 열리는데 밖에서 안 되면: 보안 그룹 인바운드(포트 · 소스) → 서브넷 라우팅 테이블에 `0.0.0.0/0 → igw-…` 경로 → 네트워크 ACL → 내 쪽 회사망이 해당 포트를 막는지(휴대폰 핫스팟으로 확인) 순서로 봅니다. 외부 인바운드가 막힌 VPC 라면 SSH · SSM 터널을 씁니다.
  ```bash
  ssh -i <키.pem> -L 3000:localhost:3000 ec2-user@<서버 IP>          # → 내 PC 에서 http://localhost:3000
  aws ssm start-session --target <인스턴스 ID> --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
  ```
- 도메인 + HTTPS(ALB · nginx 뒤): `make set k=COOKIE_SECURE v=1`, `make set k=TRUSTED_ORIGINS v=https://<도메인>`, 앞단 프록시가 X-Forwarded-For 를 채우면 `make set k=TRUST_UPSTREAM_PROXY v=1` · `make set k=TRUSTED_PROXY_HOPS v=2` 후 `make up`.

**운영**
- 관리자 비밀번호: 관리자 [사용자] 의 [비밀번호], 잊었거나 잠겼으면 `echo '새비밀번호123' | docker compose exec -T api python -m nhdip.cli admin-password 00000001` (8자 이상 · 영문 + 숫자).
- 백업은 매일 권장 — `crontab -e` 에 `0 2 * * * cd ~/2026-ax_frontier/nh-decision-platform && make backup >> backups/cron.log 2>&1` (최근 14개 보관, `BACKUP_KEEP`). 복구는 `make restore FROM=backups/<시각> CONFIRM=yes`.
- 최신 코드: `git pull && make up`. 서버를 재부팅해도 Docker · 컨테이너가 자동으로 다시 뜹니다.

---
플랫폼의 데이터 흐름 · 화면 구성 · 코드 구조 · 목데이터 기준값은 [`nh-decision-platform/README.md`](nh-decision-platform/README.md), 요구사항 · 설계는 [`nh-decision-platform/.kiro/specs/nh-decision-ai-platform/`](nh-decision-platform/.kiro/specs/nh-decision-ai-platform/) 에 있습니다.
