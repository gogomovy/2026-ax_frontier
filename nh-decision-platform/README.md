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
```

| 서비스 | 주소 | 역할 |
|---|---|---|
| web | http://localhost:3000 | 로그인 · 업무 화면 · 관리자(`/admin`) — `/backend/*` 를 api 로 프록시 |
| api | http://localhost:8000/docs | 인증 · 화면 API · 상태 API · 관리자 API |
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
- 판단 에이전트: 오케스트레이터(워크플로우 간 순서 · 대기, 설정 `orchestrator.policy`) · 변화 감지(직전값 대비 유의 변화 · 데이터 변경, 규칙 `CHANGE_SIGNIFICANCE` → 업무 화면 '최근 감지된 변화') · 플래너(서술 · 근거 검색 대상 결정, 규칙 `PLANNER_POLICY` — 바뀐 것이 없으면 LLM 미호출). 결정과 근거는 `/admin/monitor/agents`.
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
- api(8000) · neo4j(7474/7687) · litellm(4000) 포트는 개발 편의를 위해 호스트에 열려 있습니다. 운영 배포 시 web 만 노출하고 나머지는 내부망으로 제한하세요. HTTPS 환경이면 `COOKIE_SECURE=1`.
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
