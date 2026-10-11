# NH AI 경영 의사결정 플랫폼

은행 내·외부 정보를 연결하여 **경영목표의 설정과 조정을 지원하고, 그 결과를 조직 전체의 판단 기준으로 전파**하는 Agentic AI 의사결정 플랫폼.

| 구분 | 현재 상태 |
|---|---|
| 스펙 | `.kiro/specs/nh-decision-ai-platform/` — `requirements.md`(§16) · `design.md`(§19) · `tasks.md`(Phase B) |
| 프론트엔드 | Next.js 16 · React 19 — 업무 화면 3개 부서(종합기획부 · 신용리스크관리부 · 영업점) + 로그인·가입 + 관리자 화면 15종 |
| 백엔드 | FastAPI + 워커 — 인증·권한, 계산 커널, 데이터셋/문서 적재, 온톨로지(Neo4j), pgvector 검색, LiteLLM, 변경 기반 워크플로우 |
| 데이터 | 목데이터(시뮬레이션 버전)로 시드 — 실데이터는 관리자 화면에서 같은 데이터셋 정의로 업로드 |

---

## 1. 실행 (Docker, 6개 서비스)

```bash
make up          # .env 준비(비밀값 자동 생성) → 빌드 → 기동 → 최초 마이그레이션·시드·계산 자동
make admin-pass  # 최초 관리자 사번·비밀번호
make ps | logs | down | reset(볼륨 삭제) | test(백엔드 테스트) | e2e(브라우저 E2E, 기동 중인 스택 대상)
make wait-idle   # 이벤트 · 작업 처리가 끝날 때까지 대기 (기동 직후 선계산 확인)
make backup      # DB(업무 · litellm) + 업로드 파일 → backups/<시각>/
make restore FROM=backups/<시각> CONFIRM=yes   # 복구 (현재 데이터 덮어씀 · 그래프는 관리자 [온톨로지] 재투영)
make preflight   # 운영 준비 점검 · make host-check 서버 점검 · make a11y 자동 접근성 점검 · make set k=키 v=값 (.env 지정)
```

| 서비스 | 주소 | 역할 |
|---|---|---|
| web | http://localhost:3000 | 로그인 · 업무 화면 · 관리자(`/admin`) — `/backend/*` 를 api 로 프록시 |
| api | http://localhost:8000/health | 인증 · 화면 API · 상태 API · 관리자 API (문서 `/docs` 는 `API_DOCS=true` 일 때) |
| worker | - | 아웃박스 디스패처 · 워크플로우 엔진 · 임베딩 · 문서 구조화 · 그래프 투영 |
| postgres | (내부) | 원장 · 설정 · 계산 이력 · pgvector · 작업 큐 · LiteLLM DB |
| neo4j | http://localhost:7474 | 온톨로지 그래프(투영) |
| litellm | http://localhost:4000/ui | LLM 게이트웨이 (OpenAI 호환) |

**처음 사용 순서**
1. 관리자 계정으로 로그인 → `/admin/llm` 에서 LiteLLM 연결의 키를 입력하고, 프로필(또는 에이전트별) 모델명은 `coder.general.multimodal` 로 설정돼 있습니다(Q11).
   LLM 이 설정되지 않아도 모든 수치·화면은 동작하며, 서술 노드만 기존 문장으로 폴백(degraded)합니다.
2. 사용자는 `/signup` 에서 사번 8자리 + 소속(본부 > 부 > 국 > 팀 또는 지역본부 > 영업점)으로 가입 → 관리자가 `/admin/users` 에서 승인.
3. 화면 권한은 `/admin/screens` 에서 조직 단위로 부여합니다(하위 조직이 상속). 기본: 종합기획부 · 신용리스크관리부 · 수도권1지역본부 · 중부지역본부(영업점 포함).
4. 실데이터는 `/admin/datasets` 에서 업로드(당행/외부 구분 확인) → 품질 검증 → 확정 시 관련 워크플로우만 재계산.

시연용 사용자(선택): `.env` 에 `DEMO_USER_PASSWORD` 를 넣고 최초 기동하면 20250001(종합기획부) · 20250002(신용리스크관리부) · 20250003(영업점 · 수원영통지점 001068)이 생성됩니다.

**프론트만 (목데이터, 도커 없이)**: `make web-dev` → http://localhost:3000 (로그인 없이 페르소나 전환)

---

## 서버 배포 (아마존 리눅스 2023 · EC2)
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
git clone -b <브랜치> <저장소 주소> && cd <플랫폼 폴더>

# 4) 점검 → 기동
make host-check       # Docker · buildx 버전 · 메모리 · 디스크 · .env · 포트 · EC2 공인 IP — FAIL 이 있으면 안내된 명령 실행
make up               # .env 비밀값 생성 → 빌드(처음 10~20분) → 기동
make wait-idle && make ps      # 6개 모두 (healthy)
make admin-pass       # 최초 관리자 사번 · 비밀번호
make preflight        # 운영 준비 점검 (관리자 [시스템 상태] 에도 표시)
```

**외부 접속**
- 웹만 외부에 열립니다(api · LiteLLM · Neo4j 는 서버 안에서만). 80 포트로 열려면 `make set k=WEB_PORT v=80 && make up` 후 EC2 보안 그룹 인바운드에 `TCP 80` 을 추가하고 `http://<공인 IP>` 로 접속합니다.
- `.env` 값은 `make set k=<키> v=<값>` 으로 바꿉니다. `echo ... >> .env` 로 추가하면 같은 키가 두 줄이 되어 어느 값이 쓰일지 알 수 없습니다(`make host-check` 가 찾아 줍니다).
- 서버 안에서는 열리는데 밖에서 안 되면: 보안 그룹 인바운드(포트 · 소스) → 서브넷 라우팅 테이블에 `0.0.0.0/0 → igw-…` 경로 → 네트워크 ACL → 내 쪽 회사망이 해당 포트를 막는지(휴대폰 핫스팟으로 확인) 순서로 봅니다. 외부 인바운드가 막힌 VPC 라면 SSH · SSM 터널을 씁니다.
  ```bash
  ssh -i <키.pem> -L 3000:localhost:3000 ec2-user@<서버 IP>          # → 내 PC 에서 http://localhost:3000
  aws ssm start-session --target <인스턴스 ID> --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
  ```
- 도메인 + HTTPS(ALB · nginx 뒤): `make set k=COOKIE_SECURE v=1`, `make set k=TRUSTED_ORIGINS v=https://<도메인>`, 앞단 프록시가 X-Forwarded-For 를 채우면 `make set k=TRUST_UPSTREAM_PROXY v=1` · `make set k=TRUSTED_PROXY_HOPS v=2` 후 `make up`.

**운영**
- 관리자 비밀번호: 관리자 [사용자] 의 [비밀번호], 잊었거나 잠겼으면 `echo '새비밀번호123' | docker compose exec -T api python -m nhdip.cli admin-password 00000001` (8자 이상 · 영문 + 숫자).
- 백업은 매일 권장 — `crontab -e` 에 `0 2 * * * cd <플랫폼 폴더> && make backup >> backups/cron.log 2>&1` (최근 14개 보관, `BACKUP_KEEP`). 복구는 `make restore FROM=backups/<시각> CONFIRM=yes`.
- 최신 코드: `git pull && make up`. 서버를 재부팅해도 Docker · 컨테이너가 자동으로 다시 뜹니다.

---
## 2. 데이터 흐름

```
업로드(당행 bank.* / 외부 ext.*) ─ 품질 검증 ─ 버전 확정 + outbox 이벤트 (한 트랜잭션)
   └→ worker: 트리거 ∪ 계보(지표·바인딩이 참조하는 데이터셋) 매칭 → 관련 워크플로우만 작업 생성(디바운스 병합)
        load_inputs → compute_metrics(계산 커널, calc_run 기록) → judge(규칙) → build_views(화면 수치·표·차트)
        → detect_changes(변화 감지) → plan_run(플래너) → retrieve_evidence(그래프 필터 → pgvector+키워드 RRF) → narrate(LLM, [[fig:ID]] 마커만) → critic → publish(새 세대)
   (오케스트레이터: 상위 워크플로우 — 그래프 투영 · 참조 지표 — 가 끝난 뒤 하위 실행)
문서 업로드 → 청크 → 임베딩 → LLM 구조화(스키마 검증, 실패분 검토 대기 · LLM 미설정 시 별칭 규칙) → Neo4j 투영
```

- 수치는 모두 계산 커널(decimal · numpy · scipy · scikit-learn)이 계산합니다. LLM 은 계산하지 않습니다.
- 지표 정의(`/admin/metrics`) · 규칙(`/admin/rules`) · 트리거/노드(`/admin/workflows`) · 데이터셋 정의(`/admin/datasets`) · 온톨로지(`/admin/ontology`) · LLM(`/admin/llm`, `/admin/agents`) 은 모두 관리자 화면에서 바꿉니다.
- 컬럼 정의서: 종기부 컬럼정의서(T01 현황 · T02 데이터분석 · T03 목표설정)를 `/admin/contracts` 에 올리면 컬럼을 지표·서술에 연결해 `mart.hq_t01~t03` 에 적재하고, 정의서 화면값과 계산값을 대조합니다(일치 · 불일치 · 미연결).
- 정기 실행: 워크플로우별 cron 트리거(기본 06:00 · 06:10 · 06:20 KST, `/admin/workflows`)가 데이터 변경과 같은 경로로 재계산합니다.
- 질의: 업무 화면 우측 하단 `질문하기` — 권한 범위의 확정 수치(커널)와 근거 문서로만 답하고, 답변 숫자의 출처를 검증합니다. LLM 미연결 시 수치·근거만 보여줍니다.
- 판단 에이전트(LLM): 오케스트레이터(이벤트마다 영향받는 워크플로우 추가 · 실행 순서 보장) · 변화 감지(커널이 계산한 변화의 업무상 중요도 판단 → '최근 감지된 변화') · 플래너(서술 대상 · 근거 검색어 · 후속 워크플로우 결정). LLM 판단은 허용 목록으로 검증하고 미연결 · 실패 시 규칙(`CHANGE_SIGNIFICANCE` · `PLANNER_POLICY` · `orchestrator.policy`)으로 대체. 결정 · 판단 주체 · 근거는 `/admin/monitor/agents`, 프롬프트는 `/admin/agents`.
- 모니터링: `/admin/monitor/flow`(이벤트 → 매칭 사유 → 실행 → 게시) · `/admin/monitor/runs`(노드 입출력 · LLM 원문 · 계산) · `/admin/monitor/calc`(지표 값 · 추이 · 산출물 세대).

---

## 3. 화면 흐름

| 부서 | 경로 |
|---|---|
| 종합기획부 | `/hq/overview` 현황·목표 → `/hq/analysis` 데이터 분석 → `/hq/goals` 경영목표 설정 · 참고 `/hq/initiatives` `/hq/capital` |
| 신용리스크관리부 | `/risk` 현황 → `/risk/analysis/[tabKey]` 분석 결과(보고서) → `/risk/guides` 수행방안 |
| 영업점 | `/branch` 현황(업적평가 득점 · 기준 변경 알림 · 사업부문) → `/branch/analysis/[tabKey]` 영업 가이드 보고서(우량기업여신 · 서민금융) · 참고 `/branch/targets` 본부 전파 목표·가이드 |
| 공통 | `/knowledge` 데이터베이스(문서·데이터셋·용어집) |

경영목표 처리(유지·반영·직접 수정·신설)와 진행사업 등록·영업점 전파는 서버 상태로 저장되어 모든 사용자에게 공유되고, 목표 확정은 `goal.confirmed` · `rule.changed` 이벤트로 관련 수치를 다시 계산합니다.

---

## 4. 구조

```
apps/
├─ web/src/
│  ├─ app/              # 업무 화면 · login · signup · forbidden · admin/*
│  ├─ components/       # ui · layout · data · evidence · domain · providers · admin(kit) · auth
│  ├─ lib/              # data.ts(api/mock 이중 모드) · api-server · api-client · terms · types
│  ├─ proxy.ts          # (Next 16 proxy) 세션 쿠키 없으면 /login
│  └─ mock/             # 목데이터 (mock 모드 · 백엔드 시드 원천)
├─ e2e/              # 브라우저 E2E (puppeteer) — make e2e
└─ api/src/nhdip/
   ├─ models/           # iam · cfg · bank/ext(source) · calc/app/ops/audit(runtime)
   ├─ calc/             # 수식 레지스트리 · 커널 · 지표 평가
   ├─ data/             # 데이터셋 적재·품질·버전·롤백 · 문서 적재
   ├─ graph/            # Neo4j 투영 · LLM 구조화+검증 · 하이브리드 검색
   ├─ llm/              # LiteLLM 클라이언트 (에이전트별 설정 · 호출 기록)
   ├─ workflow/         # 엔진 · 노드 구현 · 디스패처
   ├─ views/            # 화면 산출물 저장(세대) · 표/차트 빌더
   ├─ api/              # auth · screens · state · admin
   └─ seed/             # 초기 설정 · 목데이터 시뮬레이션 버전 · screens/*.json(화면 목데이터 추출본)
infra/  postgres init · litellm config · scripts(ensure-env, export-mock)
.github/workflows/ci.yml  pytest · tsc · eslint · build · audit · e2e
```

화면 목데이터를 바꿨다면 `node infra/scripts/export-mock.mjs` 로 시드(`apps/api/src/nhdip/seed/screens`)를 다시 추출합니다.

---

## 5. 보안 메모

- 비밀번호 bcrypt · 세션은 서명된 HttpOnly 쿠키 + DB 세션(즉시 폐기) · 5회 실패 시 잠금 · 가입은 승인제
- LLM 키는 AES-GCM 암호화 저장(`CONFIG_ENC_KEY`), 화면에는 마스킹. `.env` 는 커밋하지 않습니다.
- api(8000) · neo4j(7474/7687) · litellm(4000) 포트는 기본으로 이 컴퓨터(127.0.0.1)에서만 열립니다(`ADMIN_BIND`). web 은 `WEB_BIND`(기본 0.0.0.0). HTTPS 환경이면 `COOKIE_SECURE=1`(HSTS 포함).
- api 는 데이터 조작만 가능한 DB 계정(`nhdip_app`, 비밀번호 `APP_DB_PASSWORD`)으로 접속해 감사 로그를 고치거나 지울 수 없습니다. 마이그레이션 · 시드 · 워커는 소유자 계정. 비우면 이전 방식.
- 속도 제한은 DB 에서 함께 셉니다(API 여러 개 가능). 사용자 IP 는 앞단 프록시(`TRUSTED_PROXIES`)가 넘긴 X-Forwarded-For 로 판정합니다. API 모드 화면은 요청마다 nonce 를 쓰는 CSP 로 스크립트를 제한합니다.
- 변경 요청(POST 등)은 같은 출처만 받습니다. 다른 주소(리버스 프록시 · 도메인)로 서비스하면 `TRUSTED_ORIGINS=https://<웹 주소>` 를 넣으세요. 운영(`NHDIP_ENV=prod`)에서는 기본 · 짧은 `SESSION_SECRET` 으로 기동하지 않습니다.
- 로그인 · 가입 · 질의 속도 제한(설정 `auth.rate_limits`), 잠금은 30분 뒤 자동 해제(`auth.lockout_minutes`, 0 = 관리자만). 보안 헤더(CSP · X-Frame-Options 등)는 web · api 모두 붙습니다.
- 개인정보: 적재할 데이터에 주민등록번호 · 휴대전화 · 이메일 · 카드번호 형식 값이 있으면 품질 검증에서 거부하고, 차주명은 화면에서 가립니다(설정 `privacy.policy`). LLM 호출 기록에도 같은 형식 값을 가려 저장합니다.
- 통제(선택): 규칙 이중 승인 `governance.dual_control`, 자동 실행 사람 승인 `orchestrator.policy.require_approval`(관리자 [에이전트 결정]에서 승인 · 반려). 운영 기록 보관 기간은 `retention.policy`(감사 로그는 정리하지 않음).
- SSO(선택): `.env` 의 `OIDC_ISSUER` · `OIDC_CLIENT_ID` · `OIDC_CLIENT_SECRET` · `OIDC_REDIRECT_URI`(`https://<웹 주소>/backend/auth/oidc/callback`) 를 넣으면 로그인 화면에 SSO 버튼이 생깁니다. 사번은 `OIDC_EMP_CLAIM` 클레임으로 기존 사용자와 연결하고 자동 가입은 하지 않습니다. 전환 후에는 `OIDC_LOCAL_LOGIN=admin`(관리자 비상 로그인만) 을 권장합니다.
- 업로드는 파싱 전에 형식 · 압축 폭탄 · 매크로 · PDF 스크립트 · DRM 을 검사합니다. 백신을 쓰려면 `UPLOAD_AV_COMMAND`(예: `clamdscan --no-summary {path}`).
- 모든 API 응답에 `X-Trace-Id` 가 붙습니다. 오류 문의 시 이 값을 관리자 [요청 추적] 화면에 넣으면 요청 → 워커 실행 → DB 구간까지 볼 수 있습니다.
- 운영 알림(선택): 관리자 [운영 알림 · 비용]에서 켜고, 채널은 `.env` 의 `ALERT_WEBHOOK_URL` · `ALERT_SMTP_*` 로 지정합니다. LLM 월 예산 · 단가는 설정 `llm.budget` · `llm.pricing`.
- 품질 점검: `make eval`(골든셋 — 기준값 · 판정 · 화면 · 서술 출처 · 검색 · 질의) · `make perf`(주요 API p95 기준치).

---

## 6. 목데이터 기준값 (시나리오 정의 반영)

| 항목 | 값 |
|---|---|
| 분석 기준일 | 2026-08-31 |
| 소기업 6B 등급 | 실제부도율 **7.929%** / 예측 대표값 **7.733%** / 최대값 **8.933%** → 대표값 초과·최대값 이내 |
| 소기업 모형 | PSI 0.082(관찰) · AR 49.62% · AR 하락률 23.8% · χ² **20.47** < 임계 21.03 (목데이터 수기값 18.42 → 커널 계산값으로 교체) |
| 소매 모형 | AS모형 AR 35.52%(하락률 34.7%) · BS모형 AR 83.84%(하락률 2.06%) |
| 포용금융 충당금 비중 | 2026.01 **7.97%** → 2026.08 **9.16%** (+1.19%p, +14.9%) → 주의 |
| 포용금융 상품코드 | 새희망홀씨 6 · 햇살론 13 · 사잇돌 2 = **21건** 전건 매칭 |
| 기업여신 | 115.34조원 · +4.04% (목표 +7.0% 대비 −2.96%p) |
| 가계여신 | 99.24조원 · +6.50% (관리목표 +4.0% 이하 초과, 잔액 한도 99.2% 소진) |
| 지주 한도 | 총자산 최대 증가율 8.2% · RWA 순증 12.4조 · 은행 목표 7.4%(여유 0.8%p) |
| 목표 추천 | 기업 +7.5~8.0% 상향 / 가계 +3.0~3.5% 이하 하향 / 포용금융 3.1~3.3조 신설 |

| 영업점(수원영통지점) | 업적평가 593.7 / 1,000점 · 지점 평균 등급 8.39(전행 6.16, 1~16) · 소기업 비중 12.7%(전행 4.4%) → 본부 추천 후보 5개 · 140억원 유치 시 평균 7.87 · 우량기업여신 +14.0점 |
| 영업점 서민금융 | 지점 비중 0.45%(전행 2.14%) · 권고 19건 · 427백만원(충당금 허용 범위 적용) · +12.7점 · 추가 충당금 20.0백만원 |

모든 시뮬레이션 수치는 화면에서 `시뮬레이션 데이터` 배지로 구분됩니다. 영업점 배점 · 가중치 · 선정 기준 · 한도는 업적평가 세부기준 원본 수령 전 시뮬레이션 가정(규칙 `BRANCH_*`)입니다.

---

## 7. 접근성·품질

- 키보드만으로 근거·계산추적·용어 도움말 접근 가능 (`focus-visible` 링 유지)
- 모든 차트에 `role="img"` + aria-label + **표로 보기** 토글
- 숫자 `tabular-nums` 고정폭, 금액 단위 라벨 상시 표기
- 하드코딩 색상·폰트 금지 — `tokens.generated.css` 변수만 사용
- Optimistic VF 는 한글 글리프가 없어 Pretendard 폴백(폐쇄망에서는 system 폰트로 자동 대체)
