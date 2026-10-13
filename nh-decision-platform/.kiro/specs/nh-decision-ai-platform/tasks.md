# 구현 태스크 — 은행 AI 경영 의사결정 플랫폼

| 항목 | 내용 |
|---|---|
| 문서 ID | NHDIP-TASK-v1.0 |
| 선행 문서 | `requirements.md`, `design.md` |
| 표기 | `_Requirements:` 요구사항 ID · `_Design:` 설계서 절 · `_DoD:` 완료 기준 |
| 규칙 | 상위 태스크는 하위 전부 완료 시에만 완료. 각 태스크는 테스트 가능한 산출물을 남긴다. |

**실행 순서 변경 (2026-09-27)**

플랫폼 구조가 복잡하여 **프론트엔드 MVP 를 먼저 구축**하고, 백엔드는 그 화면 계약에 맞춰 뒤이어 구축한다. Phase F 가 선행되고 Phase 0~9 가 후속된다.

**Phase 요약**

| Phase | 목표 | 산출 |
|---|---|---|
| **F** | **프론트엔드 MVP (목데이터)** | **계획 플로우 전체 화면 + Docker 배포** |
| **F2** | **화면 구조 재편 (목데이터)** | **부도율 추이·분석 알림·보고서 변환·진행사업 상태 모델** |
| **B (완료)** | **목데이터 기반 백엔드 일괄 구축** | **인증·관리자·LiteLLM·온톨로지·변경 기반 워크플로우 · Docker 6서비스 · E2E 34/34** |
| 0 | 프로젝트 골격·CI·인프라 | 로컬 1커맨드 기동 |
| 1 | 데이터 기반(스키마·마스터·인제스트) | 엑셀 8종 적재 + 계보 추적 |
| 2 | 결정론 계층(계산 커널·Semantic Layer·Rule) | 수식 23종 + 판정 Rule 동작 |
| 3 | 지식 계층(문서·온톨로지·검색·용어집) | 근거 검색 + 원문 추적 |
| 4 | Agent 런타임(LangGraph·검증·Provenance) | 의견 생성 + 5종 검증 통과 |
| 5 | 도메인 분석 A(신용리스크관리부) | 시나리오 B 백엔드 완성 |
| 6 | 도메인 분석 B(종합기획부·목표·전파) | 시나리오 A 백엔드 완성 |
| 7 | 프론트엔드(디자인시스템·화면) | 시나리오 A/B 화면 완성 |
| 8 | 품질·보안·운영 | 골든셋·E2E·관측성·배포 |
| 9 | 확장 슬롯(영업점·타 도메인·SHOULD) | 스켈레톤 + 후속 기능 |

---

## Phase F. 프론트엔드 MVP (완료)

> 목적: 계획한 의사결정 플로우가 **프로덕션 수준 UI/UX 로 성립하는지** 를 먼저 검증한다.
> 데이터는 목데이터를 사용하되, 반환 타입을 설계서 §11 API 응답 스키마와 동일하게 정의해 교체 비용을 0 에 가깝게 만든다.
> 구현 위치: `apps/web` · 데이터 접근 계층: `src/lib/data.ts` · 목데이터: `src/mock/*`

- [x] F.1 앱 스캐폴드 및 디자인 토큰 파이프라인
  - Next.js 14(App Router, standalone) + TypeScript strict + Tailwind 3.4, 차트·UI 외부 의존성 0
  - `designsys/DESIGN-meta.md` 토큰 → `src/styles/tokens.generated.css` CSS 변수화, Tailwind 테마는 변수만 참조
  - 한글 폴백(Pretendard) 및 `tabular-nums` 적용, 하드코딩 색상·폰트 금지
  - _Requirements:_ UX-08, UX-09, UX-10
  - _Design:_ §12.1
  - _DoD:_ 타입체크·빌드 통과, 토큰 외 색상값 미사용

- [x] F.2 목데이터 계층 (미래 API 스키마 유지)
  - `types.ts` — Figure/CalcTrace/Evidence/Insight/Goal/Proposal/ReportDoc/AnalysisTab 등 전 도메인 타입
  - `mock/finance.ts` 손익·잔액·구성비·수익성·자본제약, `mock/goals.ts` 목표 6 + 제안 3 + 검토큐 + Cascade
  - `mock/risk.ts` 모형 요약 6 + 소기업 등급 12행 + PSI 버킷 + 포용금융 21코드 + 보고서 2종 + 가이드 3 + 영업점 목표 3
  - `mock/knowledge.ts` 문서 13종·데이터셋 8종, `mock/terms.ts` 용어 12종
  - _Requirements:_ DATA-03/04, §9 데이터 자산 명세
  - _Design:_ §10.3, §11.4
  - _DoD:_ 시나리오 정의의 고정 수치(6B 7.929/7.733/8.933, 충당금 7.97→9.16, Q9 사사오입) 재현

- [x] F.3 추적성 UI (수치·근거·용어)
  - `FigureText` — hover 수식 요약 / click 계산 추적(수식·입력·원천 파일!셀)
  - `RichText` — `[[fig:ID]]`·`{{term:CODE}}` 마커 렌더, 미해결 참조는 화면에 경고로 노출
  - `EvidenceChips` + `SourceDrawer` — 3범주 Chip, 범주 부재 명시, 원문 메타·구간·원본 열기
  - `TermText` — hover/focus/click 3경로, 정의·수식·판단방법·예시·근거문서 p.N
  - `VerificationRow` / `AlignmentPanel` — Critic 5종 검증, 배치 검증 매칭·충돌
  - _Requirements:_ PRIN-03/04/05/06/07, UX-02/03/04, DB-07, AGT-06, MDL-09, DB-10
  - _Design:_ §6.4, §7.3, §9.4, §12.3
  - _DoD:_ 전 화면 미해결 수치 참조 0건, 근거·계산추적·용어가 키보드로 접근 가능

- [x] F.4 종합기획부 화면 (P1)
  - 은행 Dashboard(사업부문 7 Card, AI Attention 4건·랭킹 근거, 확인·보고 요청 3건 분리, 검토 반영)
  - 여신 상세 4화면(종합수익·기업·가계·비교) + Agent 해설 + 목표 대비 게이지
  - 총자산·RWA·수익성 화면(지주 한도·배분 소진율·BIS 시산·`시산 불가` 처리·대리지표 안내)
  - 경영목표 설정(좌 목표 List·상태·변경 이력 / 우 제안 카드: 판단·추천범위·Rule 입력·제약 검증·근거·액션 3종·직접 입력)
  - 데이터베이스(정부정책·경영의사결정·모형방법론·용어집·엑셀 품질)
  - _Requirements:_ DASH-01~07, LOAN-01~11, AST-01~10, GOAL-01~17, DB-01~11, PROP-03
  - _Design:_ §12.2, §12.4 ①②
  - _DoD:_ 요구사항 §13.1 시나리오 A 1~11단계 화면 조작으로 완주

- [x] F.5 신용리스크관리부 화면 (P2)
  - 리스크 Dashboard(일반기업 4 모형·소매 2 모형 요약, 현재 적용 경영목표, 데이터 품질, 우측 분석 결과 2건)
  - 동적 탭(의견 수만큼 신설·일 단위 재생성·이전 세대 배지)
  - HTML 보고서(목차·앵커 점프·하이라이트·상단 복귀·인쇄, 등급표 6B 하이라이트, 용어 마킹)
  - 포용금융 상세(21코드 매칭, 2시점 비중, 상품군·상품별 기여도, 익스포저·건전성, 연체율 미제공 명시)
  - 수행방안(배치 검증 후 확정·전파, 충돌 시 확정 차단)
  - _Requirements:_ CRM-01~09, MDL-01~11, INC-01~09
  - _Design:_ §12.4 ③④, §8.4, §8.5
  - _DoD:_ 요구사항 §13.2 시나리오 B 1~11단계 화면 조작으로 완주

- [x] F.6 영업점·확장 슬롯
  - 영업점 전파 목표·가이드라인·진행률, 상향 등록 스켈레톤
  - 미구현 도메인 공통 플레이스홀더(예정 범위 안내)
  - _Requirements:_ BR-01~04
  - _DoD:_ 전파된 가이드가 영업점 화면에서 출처 목표·수행방안과 함께 확인됨

- [x] F.7 Docker 배포
  - 멀티스테이지 이미지(deps → builder → runner, 비루트 실행), `docker compose up -d web`
  - backend / graph / vector 는 profile 로 분리해 MVP 기동에서 제외
  - _Design:_ §14.2
  - _DoD:_ 이미지 빌드 성공, 18개 주요 라우트 HTTP 200, `/api/health` 200

## Phase F2. 화면 구조 재편 (완료 · 2026-10-06)

> 계획 플로우를 화면으로 검증하는 과정에서 확정된 구조 변경. 백엔드는 이 구조를 기준으로 구축한다.

- [x] F2.1 화면 밀도 정리 및 진입 경로 고정
  - `/` → `/hq/overview` 리다이렉트, 페르소나별 3단계 Navigation 고정(참고 화면은 보조 링크)
  - `SectionHead`/`TextLink`/`MetricStrip` 도입 — 섹션 머리말 1줄, 섹션당 링크 1개, 지표 카드 남립 제거
  - 중복 고지 제거: 데이터 성격(`시뮬레이션 데이터`)은 PageHeader 1곳, `SIM` 배지·반복 각주 삭제
  - _Requirements:_ UX-08/09/10
  - _Design:_ §12.2, §12.3

- [x] F2.2 신용리스크관리부 1화면 재구성
  - 월별 부도율 추이 상단 배치 — 기업 규모별 5구분(대기업/외감/비외감/소기업/기업형소호), 개인 풀별 5종(임시 구분 명시), 계열 토글 + 표 전환
  - 모형 지표표(PSI·AR·AR하락률·K-S·AUROC)는 참고 정보로 하단 이동
  - 분석 결과는 본문에서 빼고 상단 알림 요약으로 전환 → 선택 시 2화면 해당 탭 직결
  - 종합기획부로 이탈시키던 `목표 화면` 링크 제거(현재 적용 목표는 표시만)
  - _Requirements:_ CRM-01~04, MDL-13
  - _Design:_ §12.4 ③
  - _DoD:_ 계열별 최신 부도율·기준월 대비 pp·심각도가 계산 추적과 함께 표시, 알림 클릭 시 탭 이동

- [x] F2.3 분석 결과 화면 정리
  - Agent 의견 영역 스크롤 추종(글래스 오버레이) 제거 — 본문 맨 위 고정 블록으로 전환
  - 탭별 전용 요약 섹션 제거(포용금융 충당금 비중 테이블 섹션) → 모든 탭이 의견 → 보고서 본문 순서로 통일
  - `분석의 한계` 별도 블록 제거(섹션 서술·변환 문서에 포함)
  - 보고서 변환·다운로드 추가 — 보고서 모델 직렬화, 수치는 계산 결과 포맷, 차트는 표로 대체, 미해결 참조 본문 명시
  - _Requirements:_ MDL-08/14, INC-05
  - _Design:_ §8.4 보고서 변환, §12.4 ④
  - _DoD:_ 두 탭 모두 변환 산출물에서 미해결 수치 참조 0건, 6B 하이라이트 행 유지

- [x] F2.4 수행방안 → 진행사업 상태 모델
  - 좌 진행중인 사업 / 우 Agent 제안안 배치(종합기획부 목표 화면과 좌우 맥락 일치)
  - `진행사업 등록` ↔ `등록 해제` 전환 시 근거 3범주·지표·배치 검증 결과 승계
  - 영업점 전파를 비가역 확정에서 `영업점 참고 가능/중단` 토글로 변경
  - 사업·분석 직접 추가(제목·내용·근거·지표·점검주기·연결 분석) + 수정 + 삭제
  - `종합기획부 보고 등록` 버튼 제거 → 등록 상태 자체가 공유 경로
  - 전파 경로를 하단 섹션에서 내부 탭으로 이동(종합기획부 3화면도 동일 적용)
  - _Requirements:_ CRM-06~14, PROP-03
  - _Design:_ §4.2 `rm.action_plan`, §12.4 ⑤
  - _DoD:_ 등록/해제·토글·수정·삭제가 전파 경로 트리와 종합기획부 화면에 즉시 반영

- [x] F2.5 종합기획부 `사업부서별 진행 사업 현황` 신설
  - 사업부서 선택 → 진행사업 카드(상태·배치 검증·영업점 참고 상태·근거·연결 분석 보고서)
  - 등록 대기 부서 플레이스홀더, 빈 상태에서 등록 경로 안내
  - _Requirements:_ PROP-06
  - _Design:_ §12.4 ⑥
  - _DoD:_ 사업부서에서 등록 해제 시 이 화면에서도 제외됨

- [x] F2.6 프로덕션 UI 재설계 (2026-10-06)
  - 좌측 사이드바 셸(업무 흐름 3단계 · 참고 · 처리 대기 배지 · 데이터 기준 1회 고지), 모바일 드로어
  - 목록 → 우측 상세 시트 패턴: 경영목표(Attention·요청·목표·AI 제안·직접 추가), 수행방안(보기·수정·직접 추가), 진행 사업(조회 전용)
  - 행에서 끝나는 동작만 행에 노출(진행사업 등록, 영업점 참고 토글), 화면 하단 다음 단계 1개
  - 근거 표시 축약(본문 `근거 N건` 버튼 / 시트 3범주 행), 시트 위 근거 드로어 계층 + Esc 단계 닫기
  - 영업점 화면에 참고 가능 사업부서 가이드 노출, 404 화면, 파비콘
  - _Requirements:_ UX-01/02/07/10, CRM-08~14, PROP-06
  - _Design:_ §12.2 상호작용 규칙, §12.3, §12.4
  - _DoD:_ 타입체크·빌드 통과, 19개 경로 응답(404 포함) 정상, 헤드리스 브라우저 상호작용 시나리오 33/33 통과(중첩 인터랙티브 요소 0, 모바일 가로 넘침 0, 콘솔 오류 0)

### Phase F 이후 남은 프론트 과제 (백엔드 연동 시)
- [x] F.8 `src/lib/data.ts` 를 실 API 호출로 교체 (`NEXT_PUBLIC_DATA_SOURCE=api`) — B.8/B.9 (`/screens/*`, 세션 쿠키 전달 · 권한 403)
- [x] F.15 `PlanStateProvider`(현재 localStorage) 를 `/plans/*` API 로 교체 — 진행사업 등록·해제·토글·수정·삭제를 서버 상태로 이전 (CRM-08~13) — `/state/plans/*` (API 모드), 경영목표는 `/state/goals/*`
- [x] F.16 전파 경로 트리를 클라이언트 재계산(`useCascadeModel`)에서 `/cascade/{goal_id}` 응답으로 교체 (PROP-03) — `GET /cascade/tree` · `/cascade/{id}`(서버 계산), 응답 전에는 같은 규칙의 낙관적 표시, 기본 트리의 같은 수행방안은 현재 상태 노드로 교체
- [x] F.17 보고서 변환을 클라이언트 Blob 생성에서 `/reports/{id}/export` 다운로드로 교체(PDF·HWP 포맷 포함) (MDL-14) — PDF · HWPX · HWP · HTML, 형식 메뉴는 설정 `report.export_formats`, 내려받기 감사 기록(Q21)
- [x] F.18 개인 풀 코드 확정 반영 — 임시 `pool_1~5` 라벨을 실제 풀 정의로 교체 (MDL-13) — 설정 `risk.segment_labels` → 데이터 구분명 순으로 표시(노드 `apply_segment_labels`, 설정 변경 시 모형 모니터링만 재실행). 실제 풀 코드 수령 시 설정만 교체(Q31)
- [x] F.9 온디맨드 분석 SSE 연결 및 `AgentProgress` 단계 표시 (UX-05) — `POST /analysis/run` · `GET /analysis/stream`(SSE), 보고서 · 데이터 분석 화면 `분석 다시 실행`, 완료 시 화면 새로고침(Q30)
- [x] F.10 자연어 추가 질문 패널 연결 (UX-06) — `POST /assist` + 사이드 시트 `질문하기`: 개념 해석 → 권한 범위 지표(커널 값) → 그래프 필터 검색 → LLM(calc_* 도구) → 숫자 출처 검증, LLM 미연결 시 수치·근거만
- [x] F.11 문서 업로드·메타데이터 등록 실동작 (DB-02/03/05/11) — 관리자 [데이터셋·문서]: 당행/외부 · 분류 · 발행기관 · 버전, 청크 → 임베딩 → 구조화
- [x] F.12 원본 문서 뷰어(페이지·하이라이트) 연결 (DB-07) — `/knowledge/doc`(면 목록 · 이전/다음 · 인용 하이라이트 · 원본 파일 열기), `GET /documents/view` · `/documents/{origin}/{id}/file`(감사 `document.open`), 근거 드로어 `원본 열기` · 문서 목록 제목 링크 (Q24)
- [x] F.13 SSO 연동 및 페르소나 스위처 제거 (AUTH-01/05) — OIDC Authorization Code + PKCE(`/auth/oidc/*`, 기본 꺼짐 · 환경변수로 켬), 사번 클레임 매핑 · 자동 가입 없음, 사번 로그인 범위 all/admin/none, API 모드 페르소나 스위처 미표시(Q32)
- [x] F.14 E2E 자동화로 시나리오 A/B 고정 (QA-04) — `apps/e2e`(puppeteer, `make e2e`) 42 항목 + GitHub Actions `ci.yml` e2e 잡 (Playwright 대신 puppeteer)

---

## Phase B. 목데이터 기반 백엔드 일괄 구축 (2026-10 착수)

> 실데이터 확보 전, 현재 화면을 목데이터로 구동하는 백엔드 전체를 먼저 세운다. 데이터 형식이 바뀌어도 **설정(데이터셋 정의·매핑·트리거·LLM 설정)** 으로 흡수하도록 만든다. Phase 0~9 중 아래 항목이 이 단계에서 선행 구현되며, 실데이터 도착 시 해당 Phase 는 "정의 추가 + 검증" 위주로 축소된다.
> 근거: 요구사항 §16 (AUTH-06~10 · LLM-01~06 · EVT-01~05 · ING-01~07 · ADM-01~14 · DEP-01~04 · ONT-13~16 · CALC-09~11), 설계 §19.

- [x] B.0 계산 방식 검증
  - 목데이터 고정 수치를 라이브러리 계산으로 재현(6B 7.929 · 전체 2.753 · PSI 0.082 · χ² 채택 · 충당금 9.16)
  - 불일치 2건 보고: AUROC·AR·K-S 목데이터 수기값, 반올림 기준(9.16 vs 9.15) → 요구사항 Q9·Q10
  - _Requirements:_ CALC-01/09/10/11

- [x] B.1 인프라 — compose 6서비스(web · api · worker · postgres+pgvector · neo4j · litellm), `.env.example`, Makefile
  - _DoD:_ `make up` 후 전 서비스 healthy, 로그인 화면 표시 (DEP-01~03)
- [x] B.2 백엔드 기반 — 설정 · DB 세션 · 스키마(iam/cfg/bank/ext/calc/ops/audit) · 마이그레이션 · 비밀번호 해시 · 세션 · 키 암호화
- [x] B.3 인증·조직·화면 권한 — 가입(사번 8자리)·승인·로그인·잠금, 부>국>팀 트리, 조직 상속 화면 권한, `/me/menu`
  - _DoD:_ 권한 없는 화면 URL·API 모두 403 (AUTH-06~10)
- [x] B.4 계산 커널 — 수식 레지스트리 + calc_run 기록 + 재현 단위 테스트 (Phase 2.1~2.3 선행)
- [x] B.5 데이터 계층 — 데이터셋 레지스트리, 당행/외부 분리 적재, 버전·롤백, 품질 검증, 목데이터 시뮬레이션 버전 시드 (ING-01~07, Phase 1 선행)
- [x] B.6 온톨로지 — 스키마 v2 시드, Neo4j 투영(멱등 MERGE), 문서 LLM 구조화 + 검증 + 검토 대기, pgvector 하이브리드 검색 (ONT-13~16, Phase 3 선행)
- [x] B.7 LLM·워크플로우 — LiteLLM 클라이언트, 연결·프로필·에이전트 설정, DB 정의 워크플로우 엔진, 아웃박스 디스패처(의존 매칭·디바운스), 워커, 노드·LLM I/O 기록 (LLM-01~06, EVT-01~05, Phase 4 선행)
- [x] B.8 화면 API — 프론트 `data.ts` 계약과 같은 응답, 경영목표 처리·진행사업 상태 API (F.8 · F.15 · F.16 · F.17)
- [x] B.9 프론트 — 로그인·가입·세션 미들웨어, 서버 메뉴 기반 사이드바, API 모드 연동 (AUTH-01/08, F.13)
- [x] B.10 관리자 화면 — 시스템 상태 · 사용자 · 조직 · 화면 권한 · LLM 연동 · 에이전트 · 워크플로우 · 데이터셋 · 온톨로지 · 규칙 · 모니터링(흐름 · 실행 · 수치) · 감사 (ADM-01~14)
- [x] B.11 통합 검증 — compose 기동, 백엔드 테스트, E2E(가입→승인→로그인→업무 화면→데이터 업로드→관련 워크플로우만 실행→모니터링 확인)
  - 결과(2026-10-06): 6개 서비스 healthy · 백엔드 pytest 18건 통과(커널 재현 10 · 통합 8) · 브라우저 E2E 34/34 통과
  - 확인한 흐름: 7790 정정본 업로드 → `wf_inclusive_risk` + `wf_graph_projection` 만 실행 → 충당금 비중 9.16 → 9.45 반영 → 되돌리기 후 9.16 복원 / 목표 확정 → GOAL_TARGETS 새 버전 → 이탈 재계산 / Critic 이 리터럴 숫자 서술 차단
  - 남은 항목: LiteLLM 실모델 연결(키·모델명 입력 후 서술·구조화·임베딩 실호출 확인), 요구사항 Q9~Q12 확정, AUROC·AR·K-S 지표(기본 비활성) 활성화 여부
  - 목데이터 대비 바뀐 값: χ² 18.42(수기) → 20.47(커널, 판정 동일 '채택')
  - 후속(2026-10-06): Q9 사사오입 · Q11 `coder.general.multimodal` · Q12 본부/지역본부/영업점 조직 트리 반영, Next.js 16.3.8 업그레이드 — pytest 20 · E2E 40/40
- [x] B.12 후속 — 정기 실행 · 질의 패널 · E2E/CI
  - cron 트리거(`workflow_trigger.last_fired_at`, 업무 시간대 기준, 놓친 실행 1회) → `schedule` 이벤트 → 기존 실행 경로. 관리자 화면에 다음/최근 실행 표시
  - `POST /assist` + `질문하기` 시트 (UX-06 · CALC-10): 권한 범위 지표만, LLM 은 calc_* 도구로만 계산, 답변 숫자 출처 검증, LLM 미연결 폴백
  - `apps/e2e` + `make e2e`(42 항목), `.github/workflows/ci.yml`(api · web · e2e) — GitHub Actions 3잡 통과
  - 결과: pytest 23 · tsc · eslint · build · 브라우저 E2E 42/42
- [x] B.13 컬럼 정의서 기반 데이터 활용 (요구사항 §16.6 DCT-01~08, 설계 §19.10)
  - 정의서 파서 + `cfg.column_contract`(마이그레이션 0004) + 정의서 v2 시드(T01 37 · T02 25 · T03 40 컬럼)
  - 원천 데이터셋 `HQ_PLAN_KPI` · 지표 27종 추가 · 수식 `RANGE_REC` · 규칙 `GOAL_REC_POLICY` · 충북지역본부 조직
  - 워크플로우 노드 `materialize_contracts` → `mart.hq_t01/t02/t03` 적재 + 화면값 대조, 트리거 `contract.changed` · `HQ_PLAN_KPI`
  - 관리자 화면 `/admin/contracts`(대조 · 연결 편집 · 정의서 업로드 · 적재 행)
  - 대조로 드러난 확인 사항: Q15(Agent 산출 산식 5건) · Q16(여신 비중 기준연도) · Q17(기업 RWA 여유 기준) · Q18(지역본부 실적 원천) · Q19(3분기 수익 원천) · Q20(정의서 해석)
- [x] B.14 정의서 미결 반영 — Q10 · Q13 · Q15~Q20 추천안 적용(요구사항 §16.4)
  - 규칙 `PROPOSAL_IMPACT` · 수식 4종(PCT_AMOUNT · PROPOSED_USAGE · GROWTH_RANGE_REC · LINEAR) · 지표 12종 · `HQ_PLAN_KPI.INCLUSIVE_SUPPLY_PY`
  - 연결 `expected` 정정(Q16), T03 RWA 제안 반영 기준(Q17), 모형 AUROC·AR·K-S 활성화(Q10)
  - 결과: T01 · T02 · T03 불일치 0 · 미연결 0, pytest 26 · E2E 통과
- [x] B.17 서버 계산 전환 · 감사 · 지표 정합 (F.16 · F.17 · 1.1.5 · Q21 · Q22)
  - 전파 경로 서버 계산(`views/cascade.py`, `GET /cascade/tree` · `/cascade/{id}`), 단위 표시 설정 `format.unit_labels`
  - 보고서 서버 변환(`reports/` 요소 모델 → HTML · PDF · HWPX · HWP), `GET /reports/formats` · `/reports/{tab}/export`, 설정 `report.export_formats` · `report.pdf_fonts`, API 이미지에 `fonts-nanum`
  - 감사 로그 append-only(마이그레이션 0005)
  - AR 하락률 지표 `ard_micro`(AR_DECLINE + 규칙 `MDL_AR_BASELINE` 시뮬레이션 가정) · 판정 근거 문구 수치 마커화
  - 결과: pytest 30 · tsc · eslint · 브라우저 E2E 49/49
- [x] B.18 원본 문서 뷰어 · 관측성 (F.12 · 0.5 · Q23 · Q24)
  - 시드 문서 면별 발췌(`meta.pages`, 청크 면 번호) + 운영 DB 보강(`upgrade_seed_documents`)
  - 뷰어 API/화면, 인용 하이라이트(공백 무시 · 조각 일치), 원본 파일 경로 이탈 차단
  - 추적 ID 전 구간 기록 · 워크플로우 실행 요약 `obs`(DB 질의 수 · 소요 · 전체 소요) · 서버 오류 메시지에 추적 ID 표시
  - 결과: pytest 33 · tsc · eslint · 브라우저 E2E 55/55
- [x] B.19 운영 보강 (8.4.4 · 1.4 · 0.4 · Q25~Q27)
  - 업로드 보안 검사 `data/filecheck.py`(형식 · 매직 바이트 · 압축 폭탄 · 매크로 · 외부 연결 · PDF 스크립트 · DRM · UTF-8, 선택 백신 `UPLOAD_AV_COMMAND`), 차단 감사 `upload.rejected`
  - 품질 규칙 `period_continuity` · `max_change`(직전 현재 버전 대비), 운영 DB 1회 보강
  - 요청 추적 기록 보관 정리(30일), CI 계산 커널 커버리지 게이트 90%(`.coveragerc`, 현재 98%)
- [x] B.20 목표 추천 엔진 · Attention 점수 (2.6 · 2.5.4 · 6.2.4 · Q28 · Q29)
  - 수식 `CAGR` · `GOAL_RANGE_REC`(기조 · 추세 가중 · 상하한) · `BIS_RATIO_SIM` · `ATTENTION_SCORE`
  - 지표: 3개년 추세 · 환산 상한(지주 한도 − 안전 마진) · 가계 관리 추천 · 제약 수치(cc_corp_*) · RWA 증가분 · BIS 시산(총 RWA 수령 전 꺼짐)
  - 노드 `recommend_goals`(제안 추천범위 · 문구 · 산출 근거) · `rank_attentions`(rankScore · rankBasis · 계산 추적)
- [x] B.21 온디맨드 분석 · 표시명 · 탭 (F.9 · F.18 · 5.6 · Q30 · Q31) — SSE 진행, 구분 표시명 설정, 분석 탭 심각도 동기화, 트리거 종류 `setting`
- [x] B.22 보안 (8.4.1 · 8.4.2 · 8.4.4 · F.13 · Q32 · Q33) — OIDC SSO, 프롬프트 인젝션 방어(`llm/guard.py`), `tests/test_security.py`(SSO 거부 9종 · 인젝션 · 권한 우회 · 경로 조작 · 세션 위조)
- [x] B.23 경영목표 정합성 · 이력 (6.4.7 · 6.4.8 · Q34) — 규칙 `GOAL_CONSISTENCY`, `POST /state/goals/check`, 경고 시 사유 입력 후 강제 확정, `GET /state/goals/{id}/history`
  - 결과(B.19~B.23): pytest 98 · 계산 커널 커버리지 98% · tsc · eslint · 브라우저 E2E 57/57 · GitHub Actions 3잡 통과
- [x] B.24 원본 보고서 어댑터 · 한글 문서 (1.3.2 ~ 1.3.6 · 3.2.2 · Q35) — `data/adapters.py`(2020 · 2633 · 7790 자동 인식, 머리글 메타 · 들여쓰기 계층 · 단위 · 다단 헤더 · 합계 행 · 셀 계보, 개인 정보 미저장), `.hwpx` · `.hwp` 문서 본문 추출, `tests/test_adapters.py`
- [x] B.25 근거 선별 (3.2.3 · 3.6.1 ~ 3.6.3 · 8.4.2 · Q36) — `graph/evidence.py` 게이팅 6단계 · 우선순위 · 범주 균형, 청크 구조 경로(마이그레이션 0007), 부서한정 문서 3지점 검증
- [x] B.26 골든셋 · 성능 (8.1 · 8.3 · Q37 · Q38) — `nhdip.evals`(6범주, pytest · CI · 관리자 [골든셋 평가]), `nhdip.perf` + 기준치, 한글 변환 동시성 수정
- [x] B.27 운영 알림 · LLM 비용 (8.5 · 4.7 · Q39 · Q40) — `nhdip.alerts`(ops.alert, 마이그레이션 0008), `llm/budget.py`, 관리자 [운영 알림 · 비용]
- [x] B.28 가이드 · 영향 분석 · 계층 규칙 (2.5.3 · 6.6.3 · 0.1 · Q41 · Q42) — 규칙 `GUIDE_CATALOG` + 노드 `select_guides`, `GET /cascade/{goal}/impact`, import-linter 계약 4종(CI)
  - 결과(B.24~B.28): pytest 112 · 골든셋 6범주 100% · 계층 계약 4/4 · tsc · eslint · 브라우저 E2E 59/59 · GitHub Actions 3잡 통과
- [ ] B.16 실측 계수 교체 — `PROPOSAL_IMPACT` 가정값(0.19 · 0.49 · 0.3 · 5~12%)을 신규 취급 평균 위험가중치 · 총자산 구성비 · 성과평가 목표로 교체(실데이터 수령 시)
- [x] B.29 영업점 업적평가 영업 가이드 (시나리오 정의서 · Q43~Q50) — 수원영통지점(001068) 1화면(업적평가 득점 · 기준 변경 알림 · 사업부문) · 2화면(우량기업여신: 규모 · 등급 · 규모×등급 · 본부 추천 후보) · 3화면(서민금융: Pool · 권고 규모), 데이터셋 8 · 커널 수식 8 · 빌더 14 · 워크플로우 `wf_branch_kpi` · 영업점 열람 범위
  - 결과: pytest 115 · 커널 커버리지 95% · 계층 계약 4/4 · tsc · eslint · 브라우저 E2E 64/64
  - 남은 항목: 세부기준 원본 PDF · 실제 데이터 파일 수령 시 데이터셋 · 규칙 교체, 다지점 동시 산출
- [x] B.30 판단 에이전트 계층 (Q51~Q54) — 오케스트레이터(워크플로우 간 대기 · 즉시 실행) · 변화 감지(유의 변화 · 데이터 변경 · 변화 피드) · 플래너(서술 · 근거 검색 대상 결정), 결정 기록 `ops.agent_decision`, 관리자 [에이전트 결정], 업무 화면 '최근 감지된 변화'
  - 결과: pytest 116 · 골든셋 6범주 100% · 계층 계약 4/4 · tsc · eslint · 브라우저 E2E 66/66
  - 함께 고침: 관리자 데이터셋 버전 목록이 최근 30개만 보여 되돌리기가 쌓이면 현재 버전이 빠지던 문제(현재 버전은 항상 포함)
- [x] B.31 LLM 판단 에이전트 · 동적 흐름 (Q55~Q57) — 변화 감지 · 플래너 · 오케스트레이터 LLM 전환(검증 · 규칙 대체), 후속 워크플로우(`agent.followup`) · 이벤트 경로 지정(`route`) · 원인 연쇄 대기, 화면 하드코딩 제거(워크플로우 · 탭 키 서버 제공)
  - 결과: pytest 117(LLM 판단 경로는 모의 LLM 으로 검증) · 골든셋 100% · 계층 계약 4/4 · tsc · eslint · 브라우저 E2E 66/66
  - 확인 필요: 실제 LLM 키 연결 후 판단 품질 · 프롬프트 조정
- [x] B.32 플랫폼 점검 보완 (Q58~Q68 · 요구사항 §17) — 보안 · 신뢰성 · 기능/컴플라이언스 · 운영 점검 결과 반영
  - [x] B.32.1 보안 — 초기화 관리자만 · 진행사업 소유 확인 · 소속 기준 등록 부서 · 영업점 열람 범위 · 인사이트/메뉴 건수 범위, 로그인 · 가입 · 질의 속도 제한 · 잠금 시간 해제, CSRF Origin 검사 · 보안 헤더(CSP) · 열린 리디렉션, 운영 기본 비밀값 기동 거부 · API 문서 끔 · `/health` 문구, LLM 주소 SSRF 차단, 감사 누락 보강
  - [x] B.32.2 신뢰성 — 권고 잠금 · 게시 3방향 병합 · 데이터셋 버전 잠금 · 유일 인덱스(0010), 성공 후 이벤트 · 성공 실행 기준 감지, 디스패치 2단계 · 연쇄 차단, 작업 잠금 · 심장박동 기준 복구, 워커 심장박동 스레드 · 주기 작업 상시 · 상태 검사, 판단 LLM 대기 · 재시도 상한 · DB 기준 쉼, LLM 기록 독립 저장, 서술 입력 구분자 · 템플릿 오류 격리, 보관 정리, 알림 3종, 트랜잭션 유휴 제한
  - [x] B.32.3 기능 · 컴플라이언스 — 단위 검사 · 기준 시점 경고 · 혼합 데이터 성격 · 갱신 실패 표시 · 단위 반영, 개인정보 검사 · 화면 가림 · LLM 기록 가림, 이중 승인 · 사람 승인, 영업점 확인 · 보고 요청 등록
  - [x] B.32.4 운영 — 이미지 digest 고정 · 관리 포트 127.0.0.1 · 로그 회전 · 시간대 · 비밀번호 필수, 백업 · 복구, 처리 완료 대기(CI), 웹 대기 상한 · 오류/대기 화면
  - 결과: pytest 132(신규 `test_hardening.py` 15) · 계층 계약 4/4 · tsc · eslint · 브라우저 E2E 66/66 · 골든셋 6범주 100% · 실기동 점검(마이그레이션 0010 · 보안 헤더 · 프록시 경유 CSRF 같은 출처 200 / 다른 출처 403 · 6개 서비스 healthy)
- [x] B.33 점검 후속 (Q69~Q72 · 요구사항 §17)
  - [x] API 전용 DB 계정 — DML 만, 감사 로그 조회 · 추가만(추가 전용 트리거 해제 불가), 기동 때 멱등 준비 · 실패 시 소유자 계정
  - [x] 공유 속도 제한(`ops.rate_limit`) · 신뢰 프록시 기준 사용자 IP(`TRUSTED_PROXIES`)
  - [x] 경로 판단 선점(`outbox_event.routing_at`, 마이그레이션 0011)
  - [x] CSP nonce + strict-dynamic(API 모드) · 시트 · 드로어 포커스 가두기 · 복귀 · 프론트 단위 테스트(vitest, CI)
  - 함께 고침: 시드 · 마이그레이션이 앱 계정으로 실행되던 순서(설정 `NHDIP_USE_APP_ROLE` 이 읽히지 않던 문제)
  - 결과: pytest 137 · 커버리지 95% · 계층 계약 4/4 · vitest 18 · tsc · eslint · next build(목데이터 · API) · 브라우저 E2E 66/66(CSP 위반 없음) · 골든셋 100% · 실기동(api 접속 계정 `nhdip_app` · 감사 IP 실제 사용자)
- [x] B.33 리뷰 반영 (Q73) — 독립 코드 리뷰 지적 10건: 워커 고아 작업 · 실행 상한, 목표 확정 동시성 · 이중 승인 우회, 변화 피드 병합 순서, X-Forwarded-For 위조, 경로 판단 정체, 이벤트 원자성, 승인 행 잠금, 앱 계정 실패 시 기동 중단
  - 결과: pytest 141 · 커버리지 95% · 계층 계약 4/4 · vitest 18 · tsc · eslint · 브라우저 E2E 66/66 · 골든셋 100% · 실기동(위조 X-Forwarded-For 무시 확인)
- [x] B.34 운영 준비 (Q74~Q77) — 운영 입력 없이 할 수 있는 부분
  - [x] 자동 접근성 점검(axe-core · `make a11y` · CI) + 위반 158건 수정(글자 대비 · 이름 · 키보드 스크롤 · 선택 상자) — 23개 화면 위반 0
  - [x] 운영 준비 점검(`make preflight` · 관리자 [시스템 상태]) · 서버 점검(`make host-check`) · `.env` 지정(`make set`) · 백업 기록 · 보관 개수
  - [x] README 서버 배포(아마존 리눅스 2023 · EC2) — 도구 설치 · 점검 · 기동 · 외부 접속 · 터널 · HTTPS · 백업 cron
- [x] B.36 외부 LiteLLM (Q78 · 사용자 지시) — 관리자 [LLM 연동] 간단 설정(주소 · 키 · 모델 · 연결 확인 · 모델 목록 선택), 주소 미입력 시 호출 안 함, 내장 LiteLLM 선택 서비스(기본 꺼짐), 예전 기본 주소 정리, 프로필 표 접근 가능한 이름
  - 결과: pytest 144 · vitest 18 · E2E 67/67 · 접근성 24개 화면 위반 0 · 실기동 5개 서비스 healthy
  - [x] 외부 LiteLLM 주소 · 키 · 모델 입력 후 서술 · 판단 품질 점검 → B.37
- [x] B.37 외부 LiteLLM 실연동 (사용자 지시 2026-10-11 · Q83) — 사내 게이트웨이 · claude-sonnet-5 로 에이전트 실검증
  - [x] 간단 설정으로 주소 · 키(DB 암호화 저장) · 모델 · 임베딩(amazon.titan-embed-text-v2:0, 1024차원) 연결
  - [x] 거부된 파라미터(temperature) 자동 제외 · 모델별 기억 · `params.dropped` 기록 + 시험
  - [x] 워크플로우 4종 실행: 변화 감지 · 오케스트레이터 JSON 판단, 플래너 by=llm, 서술 → Critic 통과, 질의 mode=llm 수치 출처 검증, 임베딩
- [x] B.38 사업부서 · 영업점 컬럼 정의서 (DCT-09~12 · Q79~Q82)
  - [x] 파서 부서 접두 · S 시트 · 시드 JSON 2종(표 11 · 컬럼 284) · 기본 연결 · 연결 갱신
  - [x] 행 생성기 7종(커널 수식) · 다행 적재 · 원천 검사 · 문서 메타 · 연결 종류 6종 추가 · `rows_where`
  - [x] 적재 노드 3개 워크플로우 · `contract.changed` 계보 매칭 · 업로드 API 접두 · 관리자 화면 부서 선택
  - [x] 시험: 단위(파서 · 보고서 절 · 기본 연결) · 통합(목업값 6B 7.929 · 8.933 · 0.196%p · 35,000,000 일치, PSI T01=T02, HTML ALL 행만, 영업점 S99 노출 문서만, 계보)
- [x] B.39 파이프라인 시각화 (PIPE-01~07 · Q84)
  - [x] API `GET /admin/pipeline`(단계 · 원천 · 워크플로우 노드 상태 · 실시간 · 산출물 → 화면) + 설정 `pipeline.stages` + 화면 `ADMIN_PIPELINE`
  - [x] 화면 `/admin/pipeline` — 전체 지도(SVG 연결선 · 선택 강조 · 글자 목록) · 워크플로우 파이프라인(단계 · 에이전트 배지 · 상태 · 요약 · 실시간) · 판단 타임라인 · 이벤트 흐름
  - [x] 시험: API 통합(단계 설정 반영 · 부서 화면 연결) · E2E 화면 목록 · 접근성 점검 대상 추가(위반 0)
- [x] B.40 업로드 기반 에이전트 시험 (사용자 지시 · Q85~Q89)
  - [x] 정의서 · 데이터셋 정의에 맞춘 2026.09 시험 파일 생성기(`apps/e2e/fixtures/make_upload_fixtures.py` — 7790 원본 양식 · 등급별 모니터링 · Oblg_grd_def · TB_JC_PM_C_LA · 득점 현황 · PDF 2종)
  - [x] 별도 스택에서 업로드 → 이벤트 → 워크플로우 → LLM 판단 · 서술 → 화면 · mart 검증(`apps/e2e/upload-agents.mjs`, claude-sonnet-5) — 33/33 통과, 결과 `docs/에이전트_업로드시험_2026-10-11.md`
  - [x] 시험에서 찾은 문제 수정: 출력 잘림 max_tokens 자동 확대 · 판단 JSON 재요청 · 변화 후보 상한 · 관계 양끝 객체 해석 · 득점 스냅숏 중복 합산 · 유치 기업 재추천 · 단위 중복 · 질의 동의어
  - 결과(B.37~B.40): pytest 156 · 커버리지 95.6% · 계층 계약 4/4 · vitest 18 · tsc · eslint · 브라우저 E2E 68/68 · 접근성 26개 화면 위반 0 · 골든셋 100% · 업로드 시험 33/33(`make upload-test`)
- [x] B.41 React #418 하이드레이션 경고 (Q90) — 원인: 사이드바 '최근 계산' 시각의 `Intl.DateTimeFormat(hour12:false)` 자정 표기가 Node 20(`24:11`)과 브라우저(`00:11`)에서 다름 → `lib/format.formatKstDateTime`(UTC 산술) · vitest 4건
- [x] B.42 온톨로지 추출 '부분 추출' 보완 (Q91) — 근거 문장 본문 · 제목 대조(공백 · 표기 · 말줄임), 이름 해석(공백 무시 · 포함 · name 대체 · 관계 라벨), 추출 프롬프트 v2, 별칭 보강 + 운영 DB 1회 보강(`ontology-extraction-v2`) · 단위 시험 4건 · 통합 시험 1건(`test_ontology_upgrade` — 기존 DB 초기 프롬프트면 새 버전, 관리자 편집 프롬프트 · 지운 별칭 키는 보존, 1회만)
- [x] B.43 판단 입력 글자 상한 (Q92) — JSON 중간 자르기 대신 목록 뒤쪽을 덜어 냄(`fit_context`), 보내지 않은 변화 후보는 규칙 판단 · 단위 시험 2건
- [x] B.44 질의 패널 지표 찾기 (Q93) — 설정 `assist.metric_synonyms`(지표별 질의 별칭, 공백 · 조사 무시 문구 일치), 순위 함수 분리(`rank_metrics`), 골든셋 질의 6건('차이' 2건 추가) · 단위 시험 4건(시드 지표로 골든셋 순위 재현)
- [x] B.45 시험 범위 (Q94 · Q95) — 접근성 점검 탭 재점검(`A11Y_TAB_PAGES`, `/admin/pipeline` 탭 2개 추가 → 28행), 업로드 시험 LLM 없는 모드 판정 · '차이' 질의 판정(34개), CI 수동 실행 전용 `upload` 잡
  - 결과(B.41~B.45, Windows · Docker 없이 — api · worker 는 Windows Python 3.11, DB 는 WSL1 PostgreSQL 18.6 + pgvector 0.8.1, Neo4j 없음): pytest 통합 포함 167 중 166 passed(`test_antivirus_hook` 1건은 Windows 에 `sh` 가 없어 실패 · 코드 변경과 무관) · 커버리지 95.56% · 골든셋(`test_golden`, 질의 6건) · 계층 계약 4/4 · vitest 22 · tsc · eslint · next build(API 모드) · 브라우저 E2E 68/68 · 접근성 28행 위반 0(파이프라인 탭 2개 포함) · 업로드 시험 LLM 없는 모드 33/33
  - #418 비교 시험(최근 계산 시각을 KST 0시대로 · 웹 서버 Node 20): 수정 전 서버 글자 `10. 13. 24:11` → 6개 화면 모두 #418, 수정 후 `10. 13. 00:11` → 0건
  - CI(janlight `c3c2565`, run 38193624279): frontend · backend(PostgreSQL 16 · Python 3.12) · e2e(Docker compose · Neo4j · 브라우저 E2E · 접근성 · 골든셋) 성공
  - LLM 모드 업로드 시험(2026-10-12, 사용자 키 · claude-sonnet-5 · titan 임베딩, 로컬 스택) → **B.48** 참고. **미확인**: 운영(EC2) DB 반영
- [x] B.47 다지점 영업점 구조 (요구사항 §19 BRM-01~08 · 설계 §19.25 · Q97) — 사용자 지시로 자료 없이 구조 먼저. **실자료(다른 지점 득점 · 잔액 · 후보 명세) 수령 시 업로드 + 규칙 목록 추가만으로 동작**
  - [x] 범위 실행 — 설정 `workflow.scopes` · `nhdip/scopes.py`, 규칙 덮어쓰기(`EvalContext.rule_overrides` · `scope_suffix`), `BRANCH_SCOPE.office_codes = ["001068"]`(기존 지점 참조 · 지표 정의 그대로, 마이그레이션 없음)
  - [x] 지표 값 범위 코드 `<지표>@<지점>` · 직전 값 · 대체 조회 범위 우선, `$latest` 빈 선택(조건에 맞는 행이 없는 지점)
  - [x] 엔진 — 게시 전 노드 지점별 재실행(`_run_scope`) · 산출물 키 `<키>@<지점>`(기본 지점은 기존 키, 기본 실행에는 '@' 키 숨김) · 자료 없는 지점 건너뜀 · 게시 1회 · 변화 피드 공유(항목 ID 범위별) · 서술 이력 범위별 · 정의서 지점별 적재(추가 지점은 목업값 대조 생략)
  - [x] 화면 API `?office=`(대시보드 · 탭 · 보고서 · 내려받기) · `GET /screens/branch/offices` · 메뉴 건수 · 질의 답변 지표 값 범위(영업점 직원은 자기 지점만)
  - [x] 웹 — 지점 선택 상자(볼 수 있는 지점 2곳 이상일 때) · `?office=` 유지(이동 · 탭 · 내려받기) · vitest(`officeParam` · `withOffice`)
  - [x] 통합 시험 `test_branch_multi_office_scope`(001068 + 가상 지점 + 자료 없는 지점 · 열람 범위 · 001068 수치 동일)
  - 결과: 로컬 pytest 169 중 168(`test_antivirus_hook` Windows 셸) · 커버리지 95.56% · 계약 4/4 · vitest 24 · tsc · eslint, 커밋 gogomovy `ff1a10b` · janlight `5f4f83d` + `4187348`(대괄호 경로 파일 1개 복사 누락 보완), CI run 38212554128 frontend · backend · e2e 성공
  - [x] LLM 사용 상한(BRM-07 · Q98) — 설정 `workflow.scopes.<wf>.narrate_max`(기본 5): 실행당 LLM(변화 판단 · 플래너 · 서술)을 쓸 추가 지점 수, 서술이 없거나 가장 오래된 지점부터 차례로(`scopes.llm_scopes`). 나머지는 규칙 판단 · 기존 문장 유지(축소 아님), 실행 요약 `scopes[].llm` · `llmOff`. 시험 `test_scope_llm_rotation` · 다지점 시험에 상한 0 검증
  - [x] 지점 2곳 이상 E2E · 접근성 — `e2e.mjs` 8-5: 가상 지점 자료 업로드(JSON 3종) + 규칙 목록 → 지점 선택 상자 · 지점 바꾸기 · 화면 이동(다음 단계 · 득점표 알림 · 사이드바)에 `?office=` 유지 · 분석 보고서 · 탭 · 내려받기 · axe(WCAG 2.1 A/AA serious · critical 0) → 원상 복구. 사이드바(`AppShell`) · 득점표(`BranchKpiBoard`) · 사업부문(`BranchSegments`) 링크가 고른 지점을 유지하도록 보완
  - 결과(LLM 상한 · E2E): 로컬 pytest 170 중 169(`test_antivirus_hook` Windows 셸) · 커버리지 95.56% · 계약 4/4 · vitest 25 · tsc · eslint · next build, 로컬 스택(WSL1 PostgreSQL 18 · Windows api/worker · standalone 웹) 브라우저 E2E 78/78(다지점 10항목 포함) · 접근성 28행 위반 0, 커밋 gogomovy `e82c821` · janlight `cdd644b`, CI run 38219131655 frontend · backend · e2e(Docker compose · Neo4j) 성공
  - [ ] 실자료 반영(다른 지점 득점 · 잔액 · 후보 명세 수령 시 업로드 + 규칙 목록 추가)
- [x] B.48 LLM 모드 업로드 시험 · 판단 호출 보정 (남은작업 0.1 ① · 사용자 키 수령 2026-10-12)
  - 1차 34/34 통과했지만 영업점 변화 감지(후보 25건)가 규칙으로 대체됨: 출력이 1,500 → 3,000 토큰에서 잘려 6,000 으로 늘린 뒤 판단 대기 30초(고정)에 두 번 끊김(ReadTimeout) → 이어서 모형 모니터링 감지도 '쉬는 시간' 으로 규칙
  - 보정 ① 대기 시간 = max(설정 대기, 출력 상한 ÷ 50 토큰/초)(`llm.client._timeout_for`) ② 후보 수에 비례하는 판단은 처음부터 출력 상한을 둔다 — `ask_json(min_tokens)`, 변화 감지 = 600 + 후보당 240(규칙 `CHANGE_SIGNIFICANCE.llm_tokens_per_candidate`, 설정 `llm.max_tokens_cap` 이내)
  - 보정 ③ 문서 1건(`doc-sim-seomin-2026h2`)이 partial — 모델이 기조 `direction` 을 코드(expand) 대신 '확대' 로 답해 '허용 외' 로 버려짐 → 관계 정의 `rule_keywords` · 대소문자로 허용 코드에 맞춤(`graph/extraction._norm_prop`)
  - 시험: `test_judge_output_budget_and_timeout` · `test_relation_prop_values_normalized_to_codes`
  - 결과(로컬 스택 · Windows api/worker · WSL1 PostgreSQL 18 · Neo4j 없음): 업로드 시험 LLM 모드 **34/34**(보정 전 1차도 34/34) · 흐름 327초 · LLM 호출 24회 · 약 6.4만 토큰, 변화 감지 LLM 3 / 규칙 2(규칙 2건은 '후보 없음') · 플래너 LLM 5/5 · 서술 claude-sonnet-5 4건 · 문서 2건 모두 `extracted` · 질의 LLM 답변 수치 출처 검증 통과. 영업점 감지 호출: 출력 상한 6,600 으로 한 번에 끝남(39초 · 4,654 토큰). 전체 pytest 172 중 171(`test_antivirus_hook` Windows 셸) · 커버리지 95.56% · 계약 4/4, 커밋 gogomovy `58b2ad2` · janlight `7a662c5`, CI run 38227028760 frontend · backend · e2e 성공
- [x] B.46 영업점 T02 제안 버전 (Q96 · 남은작업 8.1(8)) — 다행 표에 `version` 연결 지원: 같은 기준월 · 지점의 이전 적재와 수치 · 코드 열(행 집합)이 같으면 유지, 다르면 +1(서술 · 분석 ID · 분석 일자 제외, 저장된 값끼리 비교). `BRANCH_T02.PROPOSAL_VER_NO` 미연결 → 버전, 운영 DB 는 이전 기본값일 때만 연결 갱신 · 단위 시험 1 · 통합 시험(유지 · 증가) 보강
  - 결과: 로컬 pytest 168 중 167(`test_antivirus_hook` Windows 셸) · 커버리지 95.56% · 계약 4/4, 커밋 gogomovy `447f022` · janlight `88c52d3`, CI run 38195692743 frontend · backend · e2e 성공
- [ ] B.35 운영 확정 (운영 입력 필요)
  - [ ] 운영 값: 도메인 · HTTPS(`TRUSTED_ORIGINS` · `COOKIE_SECURE`) · 앞단 프록시(`TRUST_UPSTREAM_PROXY` · `TRUSTED_PROXY_HOPS`) · 보관 기간 · 이중 승인 / 사람 승인 범위 · 백업 외부 보관 위치 · DB 계정 비밀번호 교체 주기
  - [ ] WCAG 2.1 AA — 보조기술(화면 낭독기 · 키보드 전용) 실사용 테스트 · 전문가 검토
  - [ ] 보조 글자색 변경(Q74)의 브랜드 가이드 확인
- [x] B.15 리스크관리부 · 영업점 컬럼 정의서 — 같은 방식(`contracts.dept_prefix` risk · branch)으로 추가 → **B.38 에서 완료**(사업부서 · 영업점 정의서 v1, 표 11개)

---

## Phase C. 업무 자료 등록 · 분석 에이전트 · 관리자/모니터링 · UI/UX 고도화 (2026-10-12 착수 · 요구사항 §20 · 설계 §20 · Q99~Q106)

> 사용자 요청(2026-10-12): 데이터베이스 직접 업로드, 부서 분석 화면 동적 렌더링(정제 → 동적 수행 → 범용 렌더링 에이전트, 관리자 승인), 관리자 · 모니터링 정리, 디자인 시스템 기반 UI/UX. 단계마다 검증 · 커밋 · 푸시 · CI.

- [x] C.1 디자인 시스템 기반 (UX-20 · Q106) — 의미 색 옅은 배경 · 글자 색 · 차트 팔레트 토큰, 하드코딩 색 제거(Badge · 콜아웃 · 차트), 공통 구성 요소(StatCard · EmptyState · Breadcrumbs · Advanced · KeyValueList · BarList · Timeline · StackedBars), 모바일 메뉴 대화상자
- [x] C.2 관리자 정보 구조 · 관리자 홈 (ADM-01 · ADM-02 · Q104) — 메뉴 묶음 6개(1회 보강), `GET /admin/overview`(처리할 일 · 상태 · 추이), 관리자 홈 화면, AdminPage 위치 · 요약
- [x] C.3 관리자 화면 정리 (ADM-03) — 규칙 · 워크플로 · 지표 · 설정 · 온톨로지 구조화 보기 + JSON '고급' 접기, 데이터셋 · 문서 화면 정리
- [x] C.4 모니터링 개요 · 실행 상세 (MON-01 · MON-02 · Q105) — `GET /admin/monitor/overview`, 운영 개요 화면(시간대별 실행 상태 · LLM · 이벤트 · 알림), 실행 상세 노드 타임라인, 흐름 · 수치 화면 정리
- [x] C.5 데이터베이스 자료 등록 (UPL · Q99) — 마이그레이션 0012 `ops.upload_request`, 사용자 API(`/db/uploads/*`) · 관리자 승인 API, [데이터베이스] 올리기 · 내 요청, 관리자 [자료 승인], 리소스 `db_upload`, 통합 시험
- [x] C.6 분석 레지스트리 · 범용 분석 화면 (DAG-07 · Q101 · Q102) — 설정 `analysis.spaces`, `/screens/analysis/{space}/*`, 웹 `/analysis/[space]/[tabKey]` · 기존 경로 공유 구성 요소, 보고서 블록 확장(metrics · 열 형식), `POST /admin/screens`
- [x] C.7 분석 에이전트 백엔드 (DAG-01~06 · DAG-09 · Q100 · Q103) — `cfg.analysis_agent(_version)`, 명세 검증, 정제 에이전트(LLM · 규칙), 미리보기(롤백), 승인 → 지표 · 워크플로 · 전용 에이전트 · 트리거 생성, 노드 `dynamic_task` · `render_report`, 통합 시험(정제 · 검증 · 미리보기 · 승인 · 실행 · 화면 · 인젝션)
- [x] C.8 분석 에이전트 화면 (DAG-01 · DAG-03 · DAG-04 · DAG-08) — 부서 공간 [분석 만들기](글 → 정제 → 명세 확인 · 수정 → 미리보기 → 요청), 내 분석, 관리자 [분석 에이전트](승인 · 반려 · 중지 · 재개 · 폐기)
- [x] C.9 사용자 흐름 · 업무 화면 다듬기 (UX-21) — 사이드바 묶음 · 현재 위치, 화면별 다음 할 일, 빈 상태 · 오류 안내
- [x] C.10 검증 · 문서 — E2E(자료 요청 → 승인, 분석 만들기 → 승인 → 탭), 접근성 행 추가, README · 남은작업 · 작업정리
- [x] C.11 후속 · 사용자 결정 (2026-10-12 · Q107~Q109) — 부서 데이터 책임자 승인(마이그레이션 0013 · `/db/uploads/review` · [승인할 자료]), 분석 에이전트 관리자 승인 기준(주기 · 자료 변경 · LLM 의견), 새 분석 = 기존 부서 분석 화면의 탭(종합기획부 [데이터 분석] · 별도 메뉴 정리), 실 LLM 시험(`analysis-agents-llm.mjs` · 프록시 대기 180초 · 정제 출력 상한), 시험 4건 · E2E · 문서

---

## Phase D. 질문하기 고도화 — 통합 지식 색인 · 팀별 컬렉션 · 하이브리드 검색 (2026-10-12 착수 · 요구사항 §21 · 설계 §21 · Q110~Q117)

> 사용자 요청(2026-10-12): 분석 결과도 질문하기에서 답할 수 있게 색인하고, 데이터를 담당 · 관련 팀별 컬렉션으로 나눠 팀마다 다르게 가져오며, 의미 · 키워드 · 그래프를 함께 쓰는 하이브리드 검색으로 고도화. 세부는 "프로덕션 수준 추천안" 으로 위임. 단계마다 시험 · 문서 갱신.

- [x] D.1 모델 · 마이그레이션 0014 (KB-01 · KB-04 · NFR-KB-05) — `cfg.kb_collection` · `app.kb_chunk`(tsvector 생성 열 · GIN · 해시 유일 인덱스), 모델 `models/kb.py`, `.importlinter` 에 `nhdip.knowledge` 추가
- [x] D.2 컬렉션 정의 · 접근 범위 (KB-04 · KB-05 · KB-08 · ACL-01 · ACL-02 · ACL-05) — 시드 `seed/defs_knowledge.py`(컬렉션 12개 · 설정 6종), `knowledge/access.py`(배정 규칙 · `AccessContext` · `resolve_scope` · SQL 사전 필터 — 표준 `collections` 를 가리지 않도록 `access` 로 명명)
- [x] D.3 산출물 선형화 · 청크 분할 (KB-02 · KB-10) — `knowledge/render.py`(마커 해석 · 수치 문장 · 시계열 · 보고서 블록 · 개인정보 가림 · 결정적 분할)
- [x] D.4 색인기 (KB-01 · KB-03 · KB-05 · KB-06 · KB-07) — `knowledge/indexer.py`(세대 동기화 · 멱등 upsert · 개념 태깅 · 지점 범위 · 화면 리소스 · 이동 주소), `publish` 노드에서 같은 트랜잭션 색인(savepoint), 시드 끝에서 전체 색인
- [x] D.5 유지보수 (KB-09 · NFR-KB-01) — `knowledge/maintenance.py`(대조 · 임베딩 대기 채우기 · 모델 변경 재임베딩 · `kb.indexed` 이벤트), 워커 `housekeeping` 60초 주기, 그래프 투영에 산출물 → 개념 `MENTIONS` 관계(스키마 정의는 변경 없음 — 투영이 관계 종류만 확인)
- [x] D.6 질의 이해 (RAG-03) — `knowledge/query.py`(조사 · 개념 · 개념 확장(PostgreSQL 간선 + Neo4j) · 후속 질문 재작성(규칙 + 선택 LLM))
- [x] D.7 하이브리드 검색 (RAG-01 · RAG-02 · RAG-04 · RAG-05 · RAG-06) — `knowledge/search.py`(3채널 · 가중 RRF · 게이팅 · 재순위 · 출처당 상한 · 선택 LLM 재순위 · 진단)
- [x] D.8 질문하기 API 개편 (ASK-01 · ASK-02 · ASK-03 · ASK-07 · ACL-04) — `api/assist.py`(AccessContext 생성 · 검색 호출 · 프롬프트 · 검증 · 신규 응답 필드 · 이력 · 피드백 · 감사)
- [x] D.9 관리자 API (NFR-KB-03 · NFR-KB-04) — `api/admin_knowledge.py`(상태 · 컬렉션 조회/수정 · 재색인 · 검색 진단), `nhdip.cli kb-hnsw --dim N`(부분 HNSW 인덱스 + `knowledge.search.hnsw_dim` 반영), 운영 점검 항목 `knowledge_index`(`nhdip.preflight`), 관리자 화면 `/admin/knowledge`(메뉴 [데이터와 지식 › 질문하기 색인], 탭: 색인 상태 · 컬렉션 편집(담당/공유 팀 · 공개 범위 · 화면 권한 · 가산점 · 사용 · 포함 규칙) · 사용자 관점 검색 진단, 전체 재색인 버튼)
- [x] D.10 프론트 질문하기 (ASK-04 · ASK-05 · ASK-06) — `components/assist/AssistPanel.tsx`: 출처 카드(분석 · 문서 · 용어 · 컬렉션 · 담당 표시 · 화면 열기) · 검색 상태(의미 · 그래프 사용 여부 · 다시 쓴 질문) · 내 범위(`GET /assist/scope`) · 최근 3턴 이력 전송 · 피드백. 화면 낭독기 · 키보드 실사용 점검은 수동 확인 필요
- [x] D.11 시험 · 평가 (NFR-KB-02) — 단위 · 통합(팀 경계 · 지점 · 문서 · 멱등 · 대조 · 축소 동작 · 계약), 골든셋 `knowledge` 범주(팀별 기대 · 금지 컬렉션 4건, `/admin/evals` 에 표시), 기존 시험 회귀(`tests/test_knowledge.py` 27건 + 기존 시험 갱신 3건: 프롬프트 구분자 수 · 평가 범주 집합 · 운영 점검 항목)
- [x] D.12 검증 · 문서 — 전체 pytest 209건 중 208 통과(실패 1건 `test_filecheck::test_antivirus_hook` 은 Windows 에 `false` 명령이 없어서 나는 기존 환경 문제, 이번 변경과 무관) · import-linter 4/4 · tsc · eslint · vitest 25건 · `next build` 통과.
  - **실제로 확인하지 못한 것**: 실 임베딩 모델 · 실 LLM 응답(시험은 가짜 임베딩 · 가짜 LLM), 브라우저 화면 낭독기 · 키보드 전용 실사용, 실제 분석 결과 문장 분포에서의 속도(합성 데이터로만 측정), 대용량 Neo4j 그래프의 투영 시간.
  - **후속**: 임베딩 모델 확정 후 `kb-hnsw --dim N` 실행(Q119), 미결 Q118(부서 간 공유 범위) · Q120(대화 이력 서버 보관), 실데이터 전환 후 골든셋 `knowledge` 사례 보강
- [x] D.13 대규모 · 실연동 검증과 보강 (2026-10-13) — 합성 10만 청크 부하 측정(p95 중앙값 0.95초 → 0.14초, 최대 1.5초 → 0.45초): 키워드 단계적 완화 · 후보 상한 · 부분 HNSW 생성 메모리 상향(48초) · 운영 점검 경고, 실 Neo4j 5.26 으로 투영(멱등) · 문서 그래프 채널 · 개념 확장 확인, Neo4j 차단기 지수 대기, 개념 확장 소요 진단 기록, 브라우저 실사용 점검(질문하기 패널 · `/admin/knowledge` · axe 위반 0). 결과와 조건은 설계 §21.14

---

## Phase E. 사용자 흐름 기준 UI/UX 개선 (2026-10-13 착수 · 요구사항 §22 · 설계 §22 · Q121~Q126)

> 사용자 요청(2026-10-13): [자료 올리기]에서 파일을 직접 올리는 기능이 보이지 않음 + 전체 UI/UX 를 사용자 흐름 기준으로 점검 · 개선. 역할별(종합기획부 · 신용리스크 · 영업점 · 데이터 책임자 · 관리자) 화면 캡처 38장과 코드 분석으로 발견 13건(요구사항 §22.1).

- [x] E.1 문서 — 요구사항 §22(UXF · NAV · INT · TXT · LAY · QA-E1) · 결정 Q121~Q126 · 설계 §22 · 이 목록
- [x] E.2 공통 구성 요소 — `FileDrop`(끌어다 놓기 · 키보드 · 형식 · 용량) · `useConfirm` 확인 대화상자 · 알림 성공/실패 구분 · 상태 표기 `lib/labels.ts` · 파일 이름 추천 `lib/upload-match.ts`(단위 시험)
- [x] E.3 업무 업로드 흐름 (UXF-01~04) — 파일 먼저 → 추천 → 확인 → 검사 · 요청, 못 누르는 이유 · 결과 초점 · 승인 주체 문구 통일 · 내 요청 오류 · `?target=` 깊은 링크
- [x] E.4 관리자 업로드 (UXF-05) — [데이터셋·문서] 머리 파일 놓기 → 추천 → 상세(파일 채움 · 이동 · 초점), 날짜 입력 · 형식 안내, 즉시 확정 · 강제 확정 확인
- [x] E.5 데이터베이스 화면 (UXF-04) — 행 '새 버전 올리기' · 자료 찾기 · 권한별 안내 · 품질 칸 정리
- [x] E.6 내비게이션 (NAV-01~05) — 관리자 첫 화면 `/admin` · 관리 묶음 먼저 · 업무 화면 접힘 · 관리 건수 배지(시드 보강 `admin-counts-v1`) · 가장 긴 일치 활성 · 자료 성격 표시 · 권한 없음/없는 화면 안내
- [x] E.7 위험 작업 확인 (INT-01) — 사용자(역할 · 중지 · 반려 · 비밀번호) · 버전 되돌리기 · 분석 폐기 · LLM · 자료 강제 승인
- [x] E.8 표기 · 배치 (TXT-01 · LAY-01 · INT-02) — 업무 화면 영어 · 내부 용어 정리, 실행 · 품질 상태 한국어, [질문하기] 단추 가림 해소
- [x] E.9 시험 — vitest · pytest(첫 화면 · 관리 건수 · 자료 성격) · E2E(업로드 새 흐름 · 깊은 링크 · 관리자 첫 화면 · 확인 대화상자) · 접근성
- [x] E.10 검증 · 문서 — 전체 pytest · import-linter · tsc · eslint · vitest · build · E2E · 접근성, 남은작업 · 작업정리 · README, 커밋 · 푸시 · CI
- 후속(Q126): 글자 크기 토큰 일괄 치환(약 900곳) · 긴 표 페이지 나눔 · 관리자 화면 구성 요소 통합(`AdminPage`/`PageHeader`, kit `Tabs`/`PillTabs`)
## Phase G. 온톨로지 구성 시각화 (2026-10-13 착수 · 요구사항 §23 · 설계 §23 · Q127~Q129)
> 사용자 요청(2026-10-13): 온톨로지 구성을 관리자 화면에서 보기 쉽게 시각화(3D 군집 가능, 추천 방향으로). 같은 요청의 벡터 저장소(Elasticsearch · Milvus) 전환은 다른 작업 브랜치(feat/ask-knowledge-hybrid-rag · 설계 §21.18)에서 진행 중이라 여기서 하지 않음(Q129).
- [x] G.1 문서 — 요구사항 §23(OV) · 결정 Q127~Q129 · 설계 §23 · 이 목록
- [x] G.2 수집 분리 — `graph/projection.collect_graph`(투영 결과 불변 · 근거 부가 정보), `project_all` 은 수집 + 반영
- [x] G.3 지도 계산 — `graph/ontology_map.py`(상한 · Louvain · 군집 이름 · 3D/2D 배치 · 구조 요약 · 보관), `GET /admin/ontology/map`
- [x] G.4 화면 — '구성 지도' 탭: 3D 군집 지도(회전 · 확대 · 자동 회전 · 2D) · 찾기 · 범례 · 군집 초점 · 상세 패널 · 구조도 · 표로 보기 · 원장 기준 요약
- [x] G.5 시험 — pytest(수집 = 투영 입력 · 군집 · 배치 결정성 · 상한 · API), vitest(투영 수학 · 선택), E2E(지도 · 찾기 → 상세 · 표 · 구조도), 접근성
- [ ] G.6 검증 · 문서 — 전체 pytest · import-linter · tsc · eslint · vitest · build · E2E · 접근성, 남은작업 · 작업정리 · 세션히스토리 · README, 커밋 · 푸시 · CI
- 후속: 의미 임베딩 기반 '의미 지도'(임베딩 모델 확정 후) · 지도에서 추출 검토(잘못된 관계 바로 제외)

### Phase 0~8 대비 Phase B 구현 현황 (2026-10-10 갱신)

> Phase 0~8 항목은 착수 시점 설계(§1.4 · Redis · MinIO · Milvus · LangGraph)를 기준으로 쓰였고, 설계 §19 가 이를 대체했다. 아래는 Phase B 로 **대체 구현된 범위**다. 원 항목의 체크박스는 원 DoD(원 기술 선택 포함)를 모두 충족할 때만 체크하므로, 대체 완료 항목의 상태는 이 표로 본다.

| 항목 | 상태 | Phase B 구현 · 남은 것 |
|---|---|---|
| 0.1 모노레포 | 대체 완료 | `apps/web` · `apps/api`(api·worker 동일 이미지) · `apps/e2e`, import-linter 계층 계약 4종(CI). packages 분리는 하지 않음(단일 백엔드 패키지로 충분) |
| 0.2 Compose | 대체 완료 | 6서비스(설계 §19.1), graph 장애 시 degraded 동작. Redis·MinIO·Milvus 는 설계 변경으로 제외 |
| 0.3 설정·시크릿 | 대체 완료 | Pydantic Settings · `.env.example` · `ensure-env.sh` · LLM 키 AES-GCM · SSO · 백신 명령은 환경변수 전용 |
| 0.4 CI | 대체 완료 | 계층 계약 · pytest · 계산 커널 커버리지 90% 게이트 · tsc · eslint · build(mock/api) · npm audit · compose E2E · 골든셋 · 성능 참고 측정 |
| 0.5 관측성 | 대체 완료 | 내장 추적(Q23) — traceparent 호환 추적 ID, 요청 · 감사 · 이벤트 · 실행 · LLM · DB 구간, `/admin/monitor/trace`. OTLP 내보내기 보류 |
| 1.1 스키마 | 대체 완료 | iam · cfg · bank/ext · calc · app · ops · audit · mart (Alembic 0001~0006), audit append-only 트리거 |
| 1.2 마스터 | 대체 완료 | 조직(본부·부·국·팀·지역본부·영업점) · 포용금융 21코드 · PD Master Scale(6B) — 데이터셋(master)로 관리 |
| 1.3 엑셀 인제스트 | 대체 완료 | 데이터셋 정의 기반 csv/tsv/xlsx/json · checksum · 행 `src_ref` · 업로드 보안 검사 · 2633/2020/7790 원본 양식 어댑터(자동 인식 · 셀 계보). 실제 원본 파일로 매핑 보정 필요(Q35) |
| 1.4 품질 검증 | 대체 완료 | 필수 · 키 중복 · 범위 · 허용값 · 합계 일치 · 컬럼 대소 · 최소 행 · 기간 연속성 · 급변 경고 |
| 1.5 시뮬레이션 | 완료 | `data_origin` 버전 단위 전파, 목데이터 시뮬레이션 버전 시드 |
| 2.1~2.3 커널 · 수식 | 대체 완료 | 수식 레지스트리(PSI · χ² · AUROC · AR · K-S · CAGR · BIS 시산 · 목표 추천 등) · calc_run · 재현 테스트 |
| 2.4 Semantic Layer | 대체 완료 | 지표 정의(cfg.metric: 데이터셋 조회 · 지표 · 규칙 · 설정 참조, `$latest` 토큰) · metric_value 이력 |
| 2.5 Rule Engine | 대체 완료 | 규칙 버전 · BAND 판정 · rule.changed 재계산 · ATTENTION_SCORE · GOAL_CONSISTENCY · GUIDE_CATALOG |
| 2.6 목표 추천 | 대체 완료 | GOAL_RANGE_REC(기조 · 추세 · 제약 상한/하한) · 산출 근거 · limit형(가계) 분기 (Q28) |
| 2.7 Numeric Provenance | 대체 완료 | `[[fig:ID]]` 마커 · Critic 리터럴 숫자 차단 · 질의 답변 숫자 출처 검증(사용자 제시값 구분) |
| 3.1~3.6 지식 계층 | 대체 완료 | 문서 버전 · 청크(면 번호 · 구조 경로) · HWP/HWPX 본문 · pgvector · 온톨로지 v2 · Neo4j 투영 · LLM 구조화 · RRF 검색 · 근거 게이팅/우선순위/범주 · 원본 뷰어. 스캔 문서 OCR 미착수 |
| 4.x Agent 런타임 | 대체 완료 | DB 정의 워크플로우 엔진(노드 · 트리거 · 디바운스 · 정기 실행 · 설정 트리거) · narrate · critic · 질의 도구 루프 · 인젝션 방어 |
| 5.x 신용리스크 | 대체 완료 | 모형 모니터링 · 포용금융 · 부도율 추이 재계산, 분석 탭 동기화, 보고서 서버 변환(PDF·HWPX·HWP·HTML), 진행사업 상태 API |
| 6.x 종합기획부 | 대체 완료 | 수치/표/차트 재계산 · 목표 추천 · Attention 순위 · 정합성 검증 · 이력 · 변경 영향 분석 · 전파 서버 계산 · 컬럼 정의서 대조 |
| 6.7 선계산 배치 | 대체 완료 | cron 트리거(06:00 · 06:10 · 06:20 KST) → schedule 이벤트 → 같은 실행 경로 |
| 8.1 골든셋 | 대체 완료 | `nhdip.evals` 6범주(수치 · 판정 · 화면 · 서술 출처 · 검색 · 질의), pytest · CI · 관리자 화면. 실데이터 기준값으로 교체 예정 |
| 8.2 E2E | 완료 | `make e2e` 57 항목 · CI e2e 잡 |
| 8.3 성능 | 대체 완료 | `make perf` p95 기준치 · 측정 기록(docs). 운영 장비 측정 후 기준 조정 |
| 8.4 보안 | 대체 완료 | OIDC SSO · RBAC+리소스 스코프 · audit append-only · 업로드 검사 · 인젝션 · 권한 우회 테스트. TLS 는 배포 환경(리버스 프록시) |
| 8.5 관측성 · 알림 | 대체 완료 | 추적 · 모니터링 화면 · 운영 알림(웹훅 · 메일, 기본 꺼짐) · LLM 비용/예산 |

---

## Phase 0. 프로젝트 골격과 개발 환경

- [ ] 0.1 모노레포 골격 생성
  - `apps/web`, `apps/api`, `apps/agent-worker`, `apps/batch`, `packages/domain/*`, `packages/platform/*` 디렉터리와 패키지 경계 설정
  - Python: uv 또는 poetry, ruff + mypy(strict) + pytest. TypeScript: pnpm, eslint, prettier, vitest
  - `packages/domain` → `packages/platform` 단방향 의존 규칙을 import-linter(python)와 eslint boundaries로 강제
  - _Design:_ §2.1
  - _DoD:_ 의존 방향 위반 시 CI 실패 확인

- [ ] 0.2 Docker Compose 기반 인프라·배포 구성 (개발·운영 공통)
  - core: PostgreSQL 16, Redis 7, MinIO, `api`, `worker`, `scheduler`, `web`
  - 선택 profile: `graph`(Neo4j 5) / `vector`(Milvus 2.5 + etcd) / `observability`(Langfuse·OTel·Prometheus·Grafana)
  - 미기동 프로파일에 대한 degraded 폴백 동작, healthcheck·depends_on·볼륨 영속화
  - `make build` / `make up` / `make seed` / `make logs` / `make down` 단일 커맨드
  - _Requirements:_ AGT-09, NFR-11
  - _Design:_ §1.4, §14.2
  - _DoD:_ 클린 환경에서 `make build && make up && make seed` 성공, graph/vector 미기동 상태에서도 전 화면 동작

- [ ] 0.3 설정·시크릿 관리 체계
  - Pydantic Settings 기반 환경 설정, `.env.example`, 시크릿은 환경변수/Secret Manager 참조만
  - LLM 게이트웨이(LiteLLM) 추상화 인터페이스 + Mock 프로바이더(테스트용)
  - _Requirements:_ AGT-12, SEC-06
  - _Design:_ §1.4, §13.2
  - _DoD:_ 모델 교체가 설정 1줄로 가능. 코드·로그에 시크릿 평문 없음(스캐너 통과)

- [ ] 0.4 CI 파이프라인
  - lint → typecheck → unit → integration(docker) → build 단계
  - 커버리지 게이트(계산 커널 90%), 골든셋 잡 자리 확보
  - _Requirements:_ QA-01/02
  - _DoD:_ PR에서 전 단계 실행

- [x] 0.5 관측성 기본 배선 — 내장 추적(Q23): `obs.py` 추적 ID(traceparent/X-Trace-Id) · 로그 `[trace=…]` · DB 구간 합산, 마이그레이션 0006(trace_id 4개 테이블 + `ops.request_log`), 관리자 [요청 추적] `/admin/monitor/trace`. OpenTelemetry · Langfuse 내보내기는 보류
  - OpenTelemetry SDK(FastAPI·Celery·SQLAlchemy 계측), trace_id 전파, Langfuse 콜백 핸들러
  - _Requirements:_ NFR-09
  - _Design:_ §14.1
  - _DoD:_ 단일 trace_id로 HTTP→워커→DB 구간 조회 가능

---

## Phase 1. 데이터 기반

- [ ] 1.1 PostgreSQL 스키마 마이그레이션 작성
  - [ ] 1.1.1 `md` 스키마: organization, business_domain, product, account_subject, rating_model, model_grade, metric
  - [ ] 1.1.2 `fact` 스키마: pl_product_segment, loan_balance_monthly, provision_by_product, model_monitoring_grade, model_monitoring_summary, capital_constraint, exposure_summary
  - [ ] 1.1.3 `goal` 스키마: management_goal, goal_version, goal_evidence, cascade_edge, review_queue, report_request
  - [ ] 1.1.4 `know` / `calc` / `agentic` / `rm` / `audit` 스키마
  - [x] 1.1.5 audit append-only 강제(권한 회수 + UPDATE/DELETE 차단 트리거) — 마이그레이션 0005 (UPDATE · DELETE · TRUNCATE 트리거 + PUBLIC 권한 회수)
  - _Requirements:_ ONT-03, AUTH-04
  - _Design:_ §4.1, §4.2, §13.3
  - _DoD:_ Alembic up/down 왕복 성공, audit UPDATE 시도 실패 테스트 통과

- [ ] 1.2 마스터 데이터 시드
  - [ ] 1.2.1 조직(지주·은행·종합기획부·신용리스크관리부·지역본부·영업점 샘플), 페르소나
  - [ ] 1.2.2 사업부문 7종(여신 `active`, 나머지 `placeholder`)
  - [ ] 1.2.3 과목구분 마스터: 2020 양식 과목 트리(대출금 → 기업자금대출금/가계자금대출금 → 하위 과목, 종합계) 계층 등록
  - [ ] 1.2.4 상품 마스터 + **포용금융 21개 코드**(`is_inclusive=true`) + 상품군(새희망홀씨대출/햇살론/사잇돌) + 근거 문서 링크 필드
  - [ ] 1.2.5 모형 마스터(일반기업 규모별 4종 + 소매 AS/BS) + PD Master Scale(등급별 min/mid/max, 6B = 7.733 / 8.933 포함)
  - _Requirements:_ ONT-12, INC-01, MDL-01
  - _Design:_ §4.2 `md.*`, 부록 A
  - _DoD:_ 포용금융 코드 21개 조회 쿼리 결과 일치, 6B 등급 PD 값 일치

- [ ] 1.3 엑셀 인제스트 프레임워크
  - [ ] 1.3.1 `SourceFile` 등록(MinIO 업로드, checksum, 파일명 규약 `(YYYYMM)코드_명칭.xlsx` 파싱)
  - [ ] 1.3.2 `ExcelAdapter` 프로토콜 + 레지스트리 + sniff 기반 자동 선택
  - [ ] 1.3.3 `2633` 어댑터: 계층 항목명 → parent_path 복원, 8월 누계 컬럼 식별, 필수 4항목(여신(일반)부문 이자마진 수익 / 기업자금대출금이자 / 가계자금대출금이자 / 총수익) 추출
  - [ ] 1.3.4 `2020` 어댑터: 헤더 블록(조회일자·조회사무소·단위) 메타 추출, wide→long 변환, 단위 `KRW_MN` 정규화
  - [ ] 1.3.5 `7790` 어댑터: 상품코드·상품명, `손실충당금 및 충당부채 총계` 헤더명 우선 매칭(열 위치 폴백), 합계 row 감지
  - [ ] 1.3.6 `src_cell` 기록(예: `Sheet1!X37`)으로 셀 단위 계보 확보
  - _Requirements:_ DB-11, DATA-01/02, ONT-08
  - _Design:_ §10.1
  - _DoD:_ 골든 엑셀 파일 3종에 대해 파싱 스냅샷 테스트 통과, 임의 Fact 행에서 원천 셀 역추적 성공

- [ ] 1.4 데이터 품질 검증기
  - 합계 row vs 세부 합(허용 오차 0.5%), 기간 연속성, 마스터 매칭률, 전기 대비 급변(±30%) 경고, 미매핑 코드 리포트
  - 실패 시 트랜잭션 롤백 + 불일치 행·열 리포트 생성
  - _Requirements:_ DATA-05, INC-02
  - _Design:_ §10.1
  - _DoD:_ 의도적으로 합계를 틀린 픽스처에서 적재 차단 + 리포트 생성 확인

- [ ] 1.5 시뮬레이션 데이터 계층
  - [ ] 1.5.1 `data_origin` 컬럼 전파 규칙 구현(actual/simulated/mixed)
  - [ ] 1.5.2 `seeds/simulated/*` 작성: 2026-08 모형 모니터링(6B: 7.929 고정), 2633/2020 3개년, 7790 2시점, 현재 여신 경영목표, 지주 한도·RWA 배분, 확인·보고 요청
  - [ ] 1.5.3 생성 규칙 문서화(`seed_ref`) 및 실데이터 도착 시 교체 절차 스크립트
  - _Requirements:_ DATA-03/04, CALC-07
  - _Design:_ §10.3
  - _DoD:_ 시뮬레이션 레코드만으로 전 시나리오 분석 가능. 실데이터 적재 시 simulated 자동 비활성화 스크립트 동작

---

## Phase 2. 결정론 계층 (Calc Kernel · Semantic Layer · Rule Engine)

- [ ] 2.1 Calc Kernel 기반 구조
  - `@formula` 데코레이터 레지스트리, `CalcInput`/`CalcResult` 계약, `inputs_hash` 캐시, Decimal 정밀도, 단위 검증, 결측/0분모 정책
  - `calc.formula`(수식 메타) + `calc.calc_run` 기록
  - _Requirements:_ CALC-01/03/04/05/06
  - _Design:_ §6.1, §6.3
  - _DoD:_ 동일 입력 재실행 시 동일 `calc_id` 재사용, 단위 불일치 계산 거부 테스트 통과

- [ ] 2.2 기본 수식 구현
  - `DIFF`, `GROWTH_RATE`, `SHARE`, `SHARE_DELTA_PP`, `CAGR`, `YOY`, `RETURN_ON_SCALE`, `CAP_HEADROOM`, `TOTAL_ASSET_GROWTH`, `RWA_ALLOC_CHECK`, `BIS_RATIO_SIM`
  - _Requirements:_ CALC-02, LOAN-03, AST-02~05
  - _Design:_ §6.2
  - _DoD:_ 각 수식 정상·경계·결측·0분모 케이스 테스트, 커버리지 ≥ 90%

- [ ] 2.3 모형 통계 수식 구현
  - `PSI`(ε 보정·조정내역 기록), `AUROC`, `AR_GINI`, `AR_DECLINE`, `KS_STAT`, `DEFAULT_RATE`, `SDR_RANK`(단조성 위반 구간 반환), `PD_BREACH_CHECK`(3분기 판정), `CHI_SQUARE_PD`(기대빈도 부족 시 등급 병합 + 내역 기록)
  - _Requirements:_ MDL-02/03/04/05, CALC-02
  - _Design:_ §6.2, §6.3
  - _DoD:_ 소매 보고서 값(AS모형 AR 35.52 / BS모형 AR 83.84 등) 재현 테스트, 6B `above_mid_within_max` 판정 고정 테스트 통과

- [ ] 2.4 Semantic Layer
  - [ ] 2.4.1 `md.metric` 정의 로더(YAML → DB) + 지표 카탈로그 API
  - [ ] 2.4.2 정의 → 파라미터 바인딩 SQL 컴파일러(자유 SQL 금지, 문자열 보간 금지)
  - [ ] 2.4.3 `resolve_metric(code, as_of, period_type, dims)` + `timeseries()` 도구
  - [ ] 2.4.4 `calc.metric_value` 캐시 + `data_origin` 전파
  - [ ] 2.4.5 지표 시드: TOTAL_REVENUE, LOAN_NIM_REVENUE, LOAN_NIM_SHARE, CORP_LOAN_INTEREST, HOUSEHOLD_LOAN_INTEREST, CORP_LOAN_BALANCE, HOUSEHOLD_LOAN_BALANCE, PROVISION_SHARE_INCLUSIVE, 모형 지표군
  - _Requirements:_ ONT-07, CALC-04
  - _Design:_ §5
  - _DoD:_ 지표 정의 변경만으로 조회 결과 변화, SQL 스냅샷 테스트 통과, 인젝션 시도 차단 테스트

- [ ] 2.5 Rule Engine
  - [ ] 2.5.1 선언형 Rule 로더(YAML→DB) + 버전 관리 + 변경 이력
  - [ ] 2.5.2 판정 Rule: `MDL_PSI_VERDICT`, `MDL_AR_DECLINE_VERDICT`, `MDL_PD_BREACH`, `INC_PROVISION_SHARE_TREND`, SDR 단조성, 모형 적정성 종합 판정
  - [ ] 2.5.3 가이드 카탈로그: `GUIDE_RETAIL_POOL_WATCH`, `GUIDE_PERIODIC_WATCH`, `GUIDE_RECALIBRATION`
  - [ ] 2.5.4 `ATTENTION_SCORE` 랭킹 Rule
  - [ ] 2.5.5 판정 결과에 `rule_version` 스탬프(과거 판정 보존)
  - _Requirements:_ MDL-05/06, INC-04, DASH-07, NFR-12
  - _Design:_ §7.1, §14.3
  - _DoD:_ 밴드 경계값 전수 테스트, 임계값 변경 시 과거 Finding 판정 불변 확인

- [ ] 2.6 목표 추천 엔진
  - [ ] 2.6.1 제약 상한 계산(지주 총자산 증가율 한도, RWA 한도 환산) → `ceiling`
  - [ ] 2.6.2 수익성 선호도 산출(기업·가계 규모 대비 수익률 격차)
  - [ ] 2.6.3 기조 방향 입력 인터페이스(정책·의사결정 stance)
  - [ ] 2.6.4 추세 밴드(3개년 CAGR + δ 계수) → `clamp(band, ceiling)` → `GOAL_RANGE_REC`
  - [ ] 2.6.5 산출 근거 페이로드(rule_id, inputs, ceiling, band, 제약·수익성·기조 근거)
  - [ ] 2.6.6 `limit`형 목표(가계여신 관리) 처리 분기
  - _Requirements:_ GOAL-08, AST-09/10
  - _Design:_ §7.2
  - _DoD:_ 한도 초과 추천이 산출되지 않음(속성 테스트), 추천 범위 재현성 100%

- [ ] 2.7 Numeric Provenance 파이프라인
  - [ ] 2.7.1 `refs` 맵 생성기(계산 단계에서 확정)
  - [ ] 2.7.2 리터럴 숫자 스캐너 + 화이트리스트(연도·등급코드·목차 번호)
  - [ ] 2.7.3 렌더러(포맷 `pct3`/`pct2`/`krw_mn`/`pp` + `data-calc-id` 주입)
  - _Requirements:_ CALC-08, PRIN-05, UX-03
  - _Design:_ §6.4
  - _DoD:_ 참조 없는 숫자 포함 텍스트가 검증에서 100% 탐지됨(적대적 테스트 20케이스)

---

## Phase 3. 지식 계층 (문서 · 온톨로지 · 검색)

- [ ] 3.1 문서 저장·메타데이터
  - 업로드 API(형식·MIME·매직바이트 3중 검증, 크기 제한, 악성코드 스캔 훅), MinIO 저장, `know.document` 등록(원본+메타 동시 보관 제약)
  - 버전 체인(`superseded_by`), 비활성화(삭제 대체), 접근등급(`access_class`)
  - _Requirements:_ DB-02/03/05/09/12, ONT-09, SEC-08
  - _Design:_ §4.2 `know.document`, §10.2, §13.4
  - _DoD:_ `object_key`/`checksum` 없는 문서 레코드 생성 불가(제약 위반 테스트)

- [ ] 3.2 문서 파서 파이프라인
  - [ ] 3.2.1 PDF 텍스트·좌표(PyMuPDF) + 표 추출(Docling)
  - [ ] 3.2.2 HWP/HWPX 파서, 스캔 PDF OCR(PaddleOCR ko)
  - [ ] 3.2.3 섹션 트리 추출(`1.`, `가.`, `□`, `※`, 붙임 패턴) → `section_path`
  - [ ] 3.2.4 청킹(700토큰/100오버랩, 표 무분할) + `table_json` 보존 + `bbox` 저장
  - [ ] 3.2.5 메타데이터 자동 제안(문서명·기관·기준일·적용부문·유형) → 사용자 확인 폼 연동
  - _Requirements:_ DB-02/03, QA-03
  - _Design:_ §10.2
  - _DoD:_ 샘플 보고서 표 셀 정확도 ≥ 95%, 근거 표시용 표 렌더 가능

- [ ] 3.3 용어집(Glossary) 파이프라인
  - 통계방법론·용어 해설 문서에서 `용어명/정의/계산방법/판단방법/예시` 블록 규칙 추출 + LLM 보정 → `know.term`
  - 시드 용어: PSI, AR, AR하락률, K-S, AUROC, SDR, 등급계량화(Calibration), 카이제곱 검정, PD Master Scale
  - _Requirements:_ DB-10, MDL-09, UX-04
  - _Design:_ §10.2, §4.2 `know.term`
  - _DoD:_ 각 용어에 정의·수식·판단방법·근거문서 페이지가 채워짐

- [ ] 3.4 임베딩·벡터 색인
  - BGE-m3 온프렘 서빙, Milvus 컬렉션 3종(`doc_chunks`, `terms`, `report_sections`) 생성, dense+sparse 하이브리드 + RRF + 리랭커
  - _Requirements:_ ONT-05
  - _Design:_ §9.1
  - _DoD:_ 한국어 질의로 의미·키워드 양쪽 케이스 검색 성공

- [ ] 3.5 온톨로지 구축
  - [ ] 3.5.1 `nh-dio.yaml` 스키마 정의 → Neo4j 제약·인덱스 DDL + Pydantic 모델 코드 생성
  - [ ] 3.5.2 아웃박스 이벤트 기반 투영(원장 → 그래프), 멱등 MERGE
  - [ ] 3.5.3 개념 추출·연결: `MENTIONS`(PolicyTheme/Product/Metric/Term/Organization), `DEFINES`, `QUALIFIES_AS`(포용금융 상품)
  - [ ] 3.5.4 `policy_theme` 시드(inclusive_finance, corp_loan_expansion, household_loan_control, capital_adequacy) + stance 관리 화면용 API
  - [ ] 3.5.5 재투영(Reprojection) 잡 + 동기 지연 메트릭
  - _Requirements:_ ONT-01/02/04/06
  - _Design:_ §3, §14.2
  - _DoD:_ 설계서 §3.4 Cypher 4개 질의가 기대 경로 반환, 전량 재투영 성공

- [ ] 3.6 검색·근거 서비스
  - [ ] 3.6.1 관련성 게이팅 6단계(권한·부문·시점·문서유형·의미임계·개념경로) + 거부 이유 로깅
  - [ ] 3.6.2 근거 우선순위 스코어(공식성 0.40 / 시점 0.25 / 의미 0.20 / 경로 0.15)
  - [ ] 3.6.3 `Evidence` 직렬화(3범주, locator, snippet 길이 제한) + 범주별 최소 1건 보장·부재 명시
  - [ ] 3.6.4 원본 열람 API(페이지·하이라이트) + 등급 재검증
  - _Requirements:_ DB-06/07, PRIN-03/10, GOAL-07/11, CMP-08, AUTH-03
  - _Design:_ §9.2~9.4, §13.1
  - _DoD:_ 부서한정 문서가 타 부서 질의 결과·근거 목록·원본 열람 3지점 모두에서 차단됨

- [ ] 3.7 외부 정책 수집
  - 화이트리스트 프록시 클라이언트, 공식성 판별(기관 도메인), `know.external_source` 저장, 요약 생성(전문 복제 금지), 수집 시각·URL 표시
  - _Requirements:_ DB-08, CMP-08, SEC-04
  - _Design:_ §9.3, §13.2
  - _DoD:_ 화이트리스트 외 호출 차단 + 로깅, 외부 근거가 `external_policy` 범주로 구분 표시

---

## Phase 4. Agent 런타임

- [ ] 4.1 LangGraph 기반 구조
  - `DecisionState` 정의, PostgreSQL Checkpointer, 노드 재시도·타임아웃, 부분 실패(`degraded_sources`) 처리, `agentic.agent_run` 기록(그래프/프롬프트/모델/수식 버전)
  - _Requirements:_ AGT-01/09, PRIN-09, CMP-07
  - _Design:_ §8.2, §8.3
  - _DoD:_ 노드 강제 실패 주입 시 축소 분석 완료 + 한계 표시

- [ ] 4.2 오케스트레이션·라우팅·계획
  - `supervisor`(계획·조율·집계), `router`(페르소나·도메인·분석유형·소스 분류 + 저신뢰 폴백), `planner`(분석 DAG)
  - 병렬 팬아웃(`fanout_retrieval`) 구현
  - _Requirements:_ AGT-02/03
  - _Design:_ §8.1, §8.3
  - _DoD:_ 독립 분석 병렬 실행 확인(트레이스), 저신뢰 분류 시 폴백 경로 표시

- [ ] 4.3 검색·계산 Agent
  - `data_agent`(Semantic Layer 전용), `graph_agent`(사전 정의 Cypher 템플릿), `doc_agent`(하이브리드 RAG + 게이팅), `web_policy_agent`, `calc_agent`(LLM 미개입)
  - _Requirements:_ AGT-04/05, CALC-01
  - _Design:_ §8.1
  - _DoD:_ `data_agent`가 자유 SQL을 생성할 경로가 존재하지 않음(코드 리뷰 + 인터페이스 테스트)

- [ ] 4.4 Evidence·Alignment·Critic
  - [ ] 4.4.1 `evidence_agent`: 3범주 정규화·중복 제거·우선순위 정렬
  - [ ] 4.4.2 `alignment_agent`: 방향 벡터 추출 → 경영목표/경영의사결정/정부정책 3기준 대조 → `aligned/conflict/unknown` + 충돌 구간 제시 + aligned 근거 자동 첨부
  - [ ] 4.4.3 `critic_agent`: numeric_provenance, evidence_present, causality_language, alignment, goal_consistency 5종 검증 + 재생성 루프(최대 2회) + 차단
  - [ ] 4.4.4 `agentic.verification` 기록 및 실패율 메트릭
  - _Requirements:_ AGT-06, PRIN-03/06/07, CRM-07, GOAL-15
  - _Design:_ §7.3, §8.1, §8.3
  - _DoD:_ 인과 단정 문장·근거 누락·미참조 숫자 적대적 케이스가 모두 차단되고 사용자에게 노출되지 않음

- [ ] 4.5 Narrator·보고서 생성
  - 보고문서 어투 프롬프트(4블록 구조), 참조 토큰만 출력, HTML 보고서 템플릿(섹션·표·차트 자리), 앵커 삽입, 용어 자동 마킹(`data-term`), TOC 생성, sanitize
  - _Requirements:_ MDL-07/08/09, LOAN-02/05/08, AGT-10
  - _Design:_ §8.4, §8.7, §12.5
  - _DoD:_ 보고서 내 모든 숫자에 `data-calc-id`, 최초 등장 용어에 `data-term` 부착

- [ ] 4.6 HITL·전파 게이트
  - `interrupt()` 기반 승인 대기, 상태 영속화, `/agent/runs/{id}/resume`, 승인 시에만 확정·전파 수행
  - _Requirements:_ AGT-07, PRIN-08, CMP-01
  - _Design:_ §8.3
  - _DoD:_ 세션 종료 후 재로그인하여 승인 재개 성공

- [ ] 4.7 프롬프트·비용 관리
  - `prompts/<agent>/<version>.md` 버전 관리, 토큰·비용 기록, 상한 경고, 인젝션 방어(구분자·탐지·로깅)
  - _Requirements:_ AGT-10/11
  - _Design:_ §8.7, §13.2
  - _DoD:_ 문서에 삽입된 지시문이 무시되고 인젝션 로그가 남음

---

## Phase 5. 신용리스크관리부 분석 (시나리오 B)

- [ ] 5.1 익스포저·모니터링 데이터 스키마와 로더
  - 모형별 익스포저 집계(건수·금액·등급·부도여부) 스키마, 실데이터 부재 시 시뮬레이션 사용 + 플래그
  - _Requirements:_ MDL-01, DATA-04
  - _Design:_ §4.2 `fact.model_monitoring_*`, §10.3
  - _DoD:_ 향후 실데이터가 코드 변경 없이 적재 가능(적재 설정 테스트)

- [ ] 5.2 모형 모니터링 서브그래프
  - [ ] 5.2.1 안정성(PSI) 산출 — 등급/점수 분위 구간, 기준시점 vs 2026-08
  - [ ] 5.2.2 변별력(AR·AR하락률·K-S·AUROC·등급별 부도율·SDR) 산출
  - [ ] 5.2.3 등급계량화(PD_BREACH_CHECK 등급별 + CHI_SQUARE_PD 모형별)
  - [ ] 5.2.4 특이사항 탐지 + 랭킹(severity × 익스포저 규모 × 목표연관성)
  - [ ] 5.2.5 의견 생성(6B 문장 템플릿 + refs), 가이드 생성, Alignment 검증
  - [ ] 5.2.6 모형 적정성 종합 판정
  - _Requirements:_ MDL-01~06/11, CRM-06/07
  - _Design:_ §8.4
  - _DoD:_ 2026-08 배치 실행 결과 6B 의견 문장이 요구사항 문구와 수치까지 일치

- [ ] 5.3 소매여신모형 요약
  - AS/BS 등 소매 모형군 AR·AR하락률·K-S·AUROC·등급별 불량률 서열화 + 판정(양호/보통/미흡) + 판정 임계값 표시
  - _Requirements:_ MDL-10, CRM-01/02
  - _Design:_ §8.4, §10.3
  - _DoD:_ 원천 보고서 지표 체계와 매핑 표 존재

- [ ] 5.4 HTML 모니터링 보고서
  - 섹션 구성(1.개요 / 2.안정성 분석 / 3.변별력 분석 / 4.등급계량화 / 5.특이사항·가이드), 등급별 표·차트, 앵커·TOC, 용어 마킹, `rm.html_report` 저장
  - _Requirements:_ MDL-07/08/09
  - _Design:_ §8.4, §4.2 `rm.html_report`
  - _DoD:_ 상단 의견 → 앵커 점프 → 하이라이트 → 상단 복귀 동작(API 레벨 TOC·anchor 검증)

- [ ] 5.5 포용금융 신용리스크 서브그래프
  - [ ] 5.5.1 대상 상품 선별(21코드) + 근거(성과평가 방안 5p) 연결 + 미매칭 리포트
  - [ ] 5.5.2 202601·202608 충당금 로드(`손실충당금 및 충당부채 총계`, 합계 row)
  - [ ] 5.5.3 비중·증감(pp·%) 계산 + 상품군별 분해 + 상품별 기여도
  - [ ] 5.5.4 판정(`INC_PROVISION_SHARE_TREND`) + 요약 문장 + 가이드(증가→소매풀 모니터링 / 감소·유지→정기관리)
  - [ ] 5.5.5 익스포저 건수·규모, 부도율 영향(데이터 있을 때만, 없으면 `데이터 미제공` 명시)
  - [ ] 5.5.6 근거 3범주 수집 + Alignment
  - _Requirements:_ INC-01~09
  - _Design:_ §8.5, §7.1
  - _DoD:_ 충당금 비중 수치가 원천 셀까지 추적되고, 증가/감소 두 케이스 모두 의견·가이드가 규칙대로 생성

- [ ] 5.6 동적 탭 생성·세대 관리
  - 의견 수만큼 탭 생성, 일배치 재생성, `is_current` 세대 관리, 이전 세대 열람(`이전 분석(YYYY-MM-DD)` 배지)
  - _Requirements:_ CRM-05
  - _Design:_ §4.2 `rm.analysis_tab`, §8.8
  - _DoD:_ 연속 2일 배치 후 탭 세대 교체 및 과거 탭 조회 성공

- [ ] 5.7 중점관리사항·보고·전파
  - 가이드 확정(HITL), 종합기획부 확인·보고 요청 상향 등록, 영업점 가이드 전파 + Cascade 기록
  - _Requirements:_ CRM-08/09, INC-09, PROP-05
  - _Design:_ §3.3 `CASCADES_TO`, §11.2
  - _DoD:_ 확정 시 Alignment 결과가 첨부되고 Cascade 엣지가 생성됨

- [ ] 5.8 월별 부도율 추이 집계
  - [ ] 5.8.1 `fact.default_rate_monthly` 스키마·로더(기업 규모 5구분 / 개인 풀 5종, 풀 코드 매핑은 설정으로 분리)
  - [ ] 5.8.2 `DEFAULT_RATE` 커널로 월별 집계 + 기준월 대비 `DIFF`(pp) 산출, 계보(`src_file_id`/`src_cell`) 기록
  - [ ] 5.8.3 `DR_TREND_VERDICT` Rule 적용 → 계열별 심각도
  - [ ] 5.8.4 `precompute_default_rates` 배치(월 전체 + 일 증분) 및 `/risk/default-rates` 응답
  - _Requirements:_ MDL-13
  - _Design:_ §4.2 `fact.default_rate_monthly`, §7.1 `DR_TREND_VERDICT`, §8.4, §8.8
  - _DoD:_ 계열 10종의 최근 12개월 값이 재현 가능하고, 임의 계열의 수치에서 원천까지 역추적 성공. 풀 코드 교체가 설정 변경만으로 가능

- [ ] 5.9 보고서 변환 서비스
  - [ ] 5.9.1 보고서 모델 직렬화기(섹션·표·의견·근거·한계·고지 포함), 차트 → 표 변환
  - [ ] 5.9.2 `refs` 해석 및 미해결 참조 수집 → 본문 명시 + `rm.report_export.unresolved_refs` 기록
  - [ ] 5.9.3 `rm.report_export` 저장(object_key·checksum·source_generated_at) 및 `/reports/{id}/export`
  - [ ] 5.9.4 PDF·HWP 변환기 추가(동일 모델 재사용)
  - _Requirements:_ MDL-14, CMP-01/02
  - _Design:_ §4.2 `rm.report_export`, §8.4 보고서 변환
  - _DoD:_ 동일 보고서 2회 변환 결과가 바이트 단위 동일, 미해결 참조 주입 테스트에서 문서·레코드 양쪽에 기록됨

- [ ] 5.10 진행사업(Action Plan) 상태 관리
  - [ ] 5.10.1 `rm.action_plan` / `action_plan_evidence` / `action_plan_event` 스키마 + 제약(제안안은 영업점 참고 불가)
  - [ ] 5.10.2 등록·해제 API — 근거·지표·배치 검증 결과 승계, 해제 시 영업점 참고 자동 중단
  - [ ] 5.10.3 영업점 참고 토글 API + 영업점 조회·Agent 참조 필터 반영(BR-01)
  - [ ] 5.10.4 직접 등록·수정·삭제 API(Agent 수집 근거 변경 불가, 소프트 삭제)
  - [ ] 5.10.5 배치 재생성과 사용자 상태 분리 — `in_progress`·토글 값 보존, `proposed` 만 갱신
  - [ ] 5.10.6 상태 전이 전량 감사 기록
  - _Requirements:_ CRM-08/09/10/11/12/13
  - _Design:_ §4.2 `rm.action_plan`, §8.8, §11.2 `/plans/*`
  - _DoD:_ 등록 → 해제 → 재등록 왕복 후 근거·지표 손실 0, 일배치 재실행이 등록 상태를 덮어쓰지 않음을 테스트로 고정

---

## Phase 6. 종합기획부 분석·목표·전파 (시나리오 A)

- [ ] 6.1 여신 실적 분석
  - [ ] 6.1.1 여신 종합수익: 전체 수익·여신(일반)부문 이자마진 수익·비중, 3개년 8월 누계 비교(증감액·증감률)
  - [ ] 6.1.2 기업여신: 잔액·증가율·구성비·월별 추이 + 기업자금대출금이자
  - [ ] 6.1.3 가계여신: 잔액·증가율·구성비·추이 + 가계자금대출금이자 + 관리목표 대비 수준
  - [ ] 6.1.4 기업·가계 비교 뷰(잔액·비중·추이 / 이자수익 규모)
  - [ ] 6.1.5 Agent 해설(보고문서 어투, 목표 대비 판정·이탈 폭 포함)
  - _Requirements:_ LOAN-01~11
  - _Design:_ §5.2, §8.6
  - _DoD:_ 3개년 비교 수치가 전부 Calc Trace 보유, 목표 하회 시 이탈 폭(pp) 표시

- [ ] 6.2 자본·총자산 제약
  - [ ] 6.2.1 지주 한도 등록(문서 → `fact.capital_constraint`, 출처 페이지 포함)
  - [ ] 6.2.2 은행 목표 총자산 증가율 설정 + 한도 초과 차단(한도·초과폭·근거 표시)
  - [ ] 6.2.3 부서별 RWA 한도 배분 관리 + 합계 초과 검증·소진율
  - [ ] 6.2.4 BIS 총자본비율 시산 + 관리기준 여유(bp), 데이터 부재 시 `시산 불가` 명시
  - [ ] 6.2.5 RWA 대리지표(여신금액) 사용 시 한계 문구 강제 표시
  - _Requirements:_ AST-01~04/06, CMP-04
  - _Design:_ §4.2 `fact.capital_constraint`, §6.2, §7.2
  - _DoD:_ 한도 초과 입력이 저장되지 않음, 대리지표 사용 시 한계 문구 누락 불가

- [ ] 6.3 수익성 트래킹·기조·괴리
  - [ ] 6.3.1 자산군별 3개년 수익성(규모 대비 수익률·증감률·추세) + 기여 순위
  - [ ] 6.3.2 기조 추출(정부정책·경영의사결정 DB → 기업 확대 / 가계 축소) + 근거
  - [ ] 6.3.3 기조 vs 실제 운영 괴리 탐지 + 심각도
  - [ ] 6.3.4 수익 증가 여부 판정 + 미달 시 주의 어드바이스
  - _Requirements:_ AST-05/07/08
  - _Design:_ §8.6
  - _DoD:_ 괴리 Finding이 근거(기조 문서 + 실적 수치) 양쪽을 모두 참조

- [ ] 6.4 경영목표 도메인
  - [ ] 6.4.1 목표 Aggregate·상태 머신(`ai_proposed`/`under_review`/`pending_confirm`/`active`/`archived`) + 버전·Diff
  - [ ] 6.4.2 목표 List 조회(사업부문·상태·적용기간·생성방식)
  - [ ] 6.4.3 기존 목표 수정 제안(수정 필요성 판단 + 목표값은 Rule 엔진 경유) + 근거 3종
  - [ ] 6.4.4 신규 목표 제안(포용금융 공급 확대) + 미커버 영역 탐지 + 근거 3종(공식자료 우선 정렬)
  - [ ] 6.4.5 사용자 Action(`keep`/`adopt`/`manual_edit`) + 사유·채택 여부 기록
  - [ ] 6.4.6 직접 입력 폼 처리(사업부문·내용·목표값/관리방향·적용기간·측정지표·담당조직)
  - [ ] 6.4.7 확정 전 정합성 검증(목표 간 충돌 + 상위 제약) + 강제 확정 시 사유 필수
  - [ ] 6.4.8 확정·저장·감사 기록, 변경 History 조회
  - _Requirements:_ GOAL-04~17
  - _Design:_ §4.2 `goal.*`, §7.2, 부록 B
  - _DoD:_ 요구사항 §13.1 5~9단계가 API 레벨로 통과, 충돌 시 확정 차단 확인

- [ ] 6.5 Attention·검토 큐·보고 요청
  - [ ] 6.5.1 Attention 생성(목표 이탈·실적 변화·정책 변화·의사결정·요청 — 사용자 질문 없이 선제 탐지, PRIN-02) + `ATTENTION_SCORE` 랭킹 + Calc Trace
  - [ ] 6.5.2 확인·보고 요청 관리(등록·조회·상태) — AI Attention과 분리된 데이터 경로
  - [ ] 6.5.3 `경영목표 검토에 반영` → `goal.review_queue` → 목표 화면 노출
  - _Requirements:_ DASH-03/04/05/07, GOAL-17, PROP-05
  - _Design:_ §4.2, §6.2, §11.2
  - _DoD:_ 1~2건 우선 노출 규칙과 랭킹 근거 조회 동작

- [ ] 6.6 전파(Cascade)
  - [ ] 6.6.1 확정 목표 → 사업부서 `현재 적용 경영목표` 반영(Read Model 갱신 ≤ 5초 또는 갱신 배너)
  - [ ] 6.6.2 Cascade 트리 조회(목표 → 수행방안 → 영업점 목표)
  - [ ] 6.6.3 변경 영향 분석(영향 하위 항목 + 재검토 필요 여부)
  - [ ] 6.6.4 사업부서 Agent가 참조한 목표 ID를 근거에 포함
  - [ ] 6.6.5 `사업부서별 진행 사업 현황` 조회(`/initiatives?org=`) — 등록·해제·토글 상태와 연결 보고서를 종합기획부 관점으로 집계 (PROP-06)
  - [ ] 6.6.6 전파 트리에 진행사업 편입 — 목표 수정 내역 표기, 참고 중단 사업의 영업점 노드 비활성화, 연결 목표 없는 사업의 누락 방지 그룹 (PROP-03, CRM-14)
  - _Requirements:_ PROP-01~04, CRM-03, PROP-02
  - _Design:_ §3.3, §4.2 `goal.cascade_edge`, §16.2
  - _DoD:_ 목표 확정 직후 P2 화면 조회 시 갱신된 목표가 표시

- [ ] 6.7 선계산 배치 잡 (scheduler 컨테이너 / APScheduler)
  - `precompute_p1_dashboard`, `precompute_p2_risk`, `refresh_tabs`, `goal_review_scan`, `external_policy_watch`, `quality_report`, 실패 재시도 3회 + 알림 + 전일 결과 유지
  - 잡은 CLI(`python -m nhdip.jobs run <job>`)로도 단독 실행 가능해야 한다(운영·재계산용)
  - _Requirements:_ AGT-08, NFR-04/08, PRIN-01
  - _Design:_ §8.8
  - _DoD:_ 전체 일배치 ≤ 30분, 실패 시 전일 스냅샷 유지 확인

---

## Phase 7. 프론트엔드

- [ ] 7.1 디자인 토큰 파이프라인
  - `designsys/DESIGN-meta.md` front-matter → `tokens.generated.css` + Tailwind 테마 자동 생성 스크립트
  - 한글 폰트 폴백(Pretendard Variable), `tabular-nums`, 하드코딩 색상·폰트 금지 린트 규칙
  - _Requirements:_ UX-09
  - _Design:_ §12.1
  - _DoD:_ 하드코딩 hex 사용 시 CI 실패, 토큰 문서 변경 → 재생성으로 반영

- [ ] 7.2 공통 컴포넌트
  - [ ] 7.2.1 버튼군(`primary`/`buy-cta`=확정·승인/`secondary`/`ghost`/`pill-tab`), 배지군(success/attention/warning/critical), 카드군
  - [ ] 7.2.2 `EvidenceChipGroup` + `SourceDrawer`(문서 메타·구간·표·원본 열기)
  - [ ] 7.2.3 `CalcTracePopover`(수식·입력·출처 셀·버전)
  - [ ] 7.2.4 `TermTooltip`(hover/focus/click 3경로, 정의·수식·판단방법·근거문서)
  - [ ] 7.2.5 `DataOriginBadge`, `AlignmentBadge`, `AgentProgress`(SSE), `AskAgentPanel`
  - [ ] 7.2.6 차트 래퍼(ECharts + 데이터 테이블 토글 + aria-label)
  - [ ] 7.2.7 숫자·금액 표기 유틸(단위 라벨 필수, 자릿수 규칙, tabular-nums) — UX-08
  - _Requirements:_ UX-02/03/04/05/06/07/08/10, CALC-07, PRIN-07
  - _Design:_ §12.1, §12.3
  - _DoD:_ 키보드만으로 근거·계산추적·용어 도움말 접근 가능, 대비 4.5:1 검사 통과

- [ ] 7.3 종합기획부 화면
  - [ ] 7.3.0 `AppShell` 사용자 전환을 SSO 권한 기반으로 교체(UX-01, AUTH-01/05) — 처리 대기 배지를 API 집계로 전환
  - [ ] 7.3.1 은행 Dashboard(사업부문 Card 7종, AI Attention, 확인·보고 요청 구분, 검토 반영 버튼)
  - [ ] 7.3.2 여신 상세(종합수익/기업/가계 3영역) + 각 상세 화면 + 비교 뷰
  - [ ] 7.3.3 경영목표 설정(사업부문 Card → 여신: 좌 목표 List / 우 제안 패널)
  - [ ] 7.3.4 `ProposalSheet` 액션을 `/goals/{id}/actions` 로 연결(판단·추천범위·근거 3종·제약 여유·액션 3종)
  - [ ] 7.3.5 직접 수정·신규 입력 폼, 확정 플로우(정합성 경고·사유 입력), History 타임라인
  - [ ] 7.3.6 총자산·RWA·수익성 화면(`ConstraintPanel`, 수익성 트래킹, 대리지표 한계 표시)
  - [ ] 7.3.7 데이터베이스 화면(정부정책·경영의사결정·모형방법론·[데이터] 4 Card, 업로드·메타데이터 폼·품질 상태)
  - _Requirements:_ UX-01, DASH-01~06, LOAN-01~11, AST-01~06, GOAL-01~17, DB-01~05/11, DATA-05
  - _Design:_ §12.2, §12.4 ①②
  - _DoD:_ 요구사항 §13.1 전 단계 화면 조작으로 완주

- [ ] 7.4 신용리스크관리부 화면 (F2 구조 기준으로 API 연동)
  - [ ] 7.4.1 1화면: 분석 결과 알림 → 월별 부도율 추이(`DefaultRatePanel`) → 현재 경영목표·데이터 품질 → 모형 지표표(하단)
  - [ ] 7.4.2 `DynamicTabBar`(일 단위 재생성, 이전 세대 배지)
  - [ ] 7.4.3 `HtmlReportView`(좌 TOC, 본문 맨 위 의견 블록 — 스크롤 추종 없음, 앵커 점프·하이라이트·상단 복귀)
  - [ ] 7.4.4 보고서 변환·다운로드를 `/reports/{id}/export` 로 연결(포맷 선택)
  - [ ] 7.4.5 포용금융 탭은 의견 → 보고서 본문 순서(전용 요약 섹션 없음)
  - [ ] 7.4.6 수행방안·진행사업 화면: 좌 진행사업 / 우 제안안, 등록·해제·영업점 참고 토글·직접 추가·수정·삭제를 `/plans/*` 로 연결
  - [ ] 7.4.7 전파 경로 내부 탭을 `/cascade` 응답으로 전환
  - _Requirements:_ CRM-01~14, MDL-07~10/13/14, INC-01~09
  - _Design:_ §12.4 ③④⑤
  - _DoD:_ 요구사항 §13.2 전 단계 화면 조작으로 완주

- [ ] 7.5 영업점·플레이스홀더 화면
  - 영업점: 목표·가이드 조회, 목표 대비 실적(Mock), 확인·보고 요청 상향
  - 준비 중 도메인 공통 플레이스홀더(예정 범위 안내)
  - _Requirements:_ BR-01/03
  - _Design:_ §12.2
  - _DoD:_ 전파된 가이드가 영업점 화면에 근거·기한과 함께 표시

---

## Phase 8. 품질 · 보안 · 운영

- [ ] 8.1 골든셋 평가 하네스
  - 고정 시뮬레이션 데이터에 대한 기대 수치·판정·근거 문서 ID 정답셋, 수치 정확성 100% 게이트, 근거 3범주 충족률, 인과 표현 위반 0, 배치 판정 정확도
  - 모델·프롬프트·Rule 변경 시 자동 실행, 수치 실패는 배포 차단
  - _Requirements:_ QA-01, AGT-12
  - _Design:_ §15
  - _DoD:_ 프롬프트 변경 PR에서 골든셋 자동 실행 및 차단 동작 확인

- [ ] 8.2 E2E 자동화
  - Playwright로 요구사항 §13.1 / §13.2 시나리오 각 11단계 자동화(근거·계산추적·용어 도움말 확인 포함)
  - _Requirements:_ QA-04
  - _DoD:_ CI에서 두 시나리오 통과

- [ ] 8.3 성능 검증·튜닝
  - k6 부하 시나리오로 NFR-01~06 측정, 인덱스·캐시·서버 컴포넌트 튜닝
  - _Requirements:_ NFR-01~07
  - _DoD:_ 목표치 달성 리포트

- [ ] 8.4 보안 구현·검증
  - [ ] 8.4.1 OIDC 연동 인터페이스 + 1차 Mock + 페르소나 스위처(개발 전용 플래그)
  - [ ] 8.4.2 RBAC + 리소스 스코프 2중 검증, 문서 등급 3지점 검증
  - [ ] 8.4.3 TLS·저장 암호화·시크릿 관리, 감사 로그 append-only 검증
  - [ ] 8.4.4 프롬프트 인젝션·권한 우회·업로드 악성파일 시나리오 테스트
  - _Requirements:_ AUTH-01~05, SEC-01~08, CMP-05
  - _Design:_ §13
  - _DoD:_ 프론트 우회 API 직접 호출 차단, 인젝션 무시·로깅 확인

- [ ] 8.5 관측성·알림 완성
  - 대시보드(배치 성공률, 선계산 신선도, Critic 실패율, simulated 비율, 미매핑 코드, 게이트 거부율, LLM 비용), 알림 규칙
  - _Requirements:_ NFR-09/08
  - _Design:_ §14.1
  - _DoD:_ 배치 실패·Critic 실패율 초과 시 알림 발송 확인

- [ ] 8.6 운영 도구
  - [ ] 8.6.1 임계값·Rule·프롬프트 관리 화면 + 버전 이력 + 승인 2인 원칙
  - [ ] 8.6.2 재투영·재파싱·재계산 운영 잡 실행 UI/CLI
  - [ ] 8.6.3 백업·복구 절차 문서 + 복구 리허설(RPO 24h / RTO 4h)
  - _Requirements:_ NFR-10/11/12
  - _Design:_ §14.2, §14.3
  - _DoD:_ stg에서 복구 리허설 성공 기록

- [ ] 8.7 컴플라이언스 산출물
  - 시스템 성격 고지(보조 도구), 설명가능성 패키지(근거·수식·임계값·모델 버전 내보내기), 모형 보고서 형식 내보내기, 취약계층 배제·차별 방지 검증 규칙, 이력 보존 정책 설정
  - _Requirements:_ CMP-01~10, DATA-06
  - _Design:_ §7.3, §13.3, §15
  - _DoD:_ 감사자 관점 산출물 1식 생성 가능, PII 컬럼 감지 시 적재 차단 확인

---

## Phase 9. 확장 슬롯 (SHOULD / 차기 준비)

- [ ] 9.1 도메인 레지스트리 확장성
  - 신규 사업부문을 설정(도메인 정의·지표·플레이북)만으로 추가 → Dashboard/목표/DB 기본 동작
  - _Requirements:_ BR-04
  - _DoD:_ 수신 도메인을 설정만으로 추가하는 리허설 성공

- [ ] 9.2 SHOULD 기능 묶음
  - [ ] 9.2.1 목표 변경 History 타임라인 고도화(GOAL-16)
  - [ ] 9.2.2 전파 영향 분석 UI(PROP-04)
  - [ ] 9.2.3 외부 최신 정책·기사 검색 화면(DB-08)
  - [ ] 9.2.4 자연어 추가 질문 강화(UX-06)
  - [ ] 9.2.5 모니터링 연도 간 비교(MDL-12)
  - [ ] 9.2.6 포용금융 성과평가 연계 표시(INC-10)
  - [ ] 9.2.7 비용·토큰 상한 관리(AGT-11)
  - [ ] 9.2.8 사용자 피드백 루프(QA-05)
  - [ ] 9.2.9 최신본 수집 필요 문서 목록화 화면(ONT-11)

- [ ] 9.3 실데이터 전환 준비
  - 실제 스키마 수용 테스트, 시뮬레이션 비활성화 절차, 미결 Q1~Q8 확정 반영(모형 코드 체계·임계값·추천 Rule 승인·LLM 확정·요청 원천 연동·문서 등급 체계·탭 보존 정책·영업점 배분 단위)
  - _Requirements:_ §15.2, §15.3
  - _DoD:_ 실데이터 1종 이상 적재 후 골든셋 재기준화 완료

---

## 마일스톤 제안

| 마일스톤 | 포함 Phase | 검증 기준 |
|---|---|---|
| **M0 — 프론트엔드 MVP (완료)** | **F, F2** | **시나리오 A/B 화면 완주 · 미해결 수치 참조 0 · 화면 구조 재편 반영 · Docker 기동** |
| M1 — 데이터·계산 기반 | 0, 1, 2 | 엑셀 8종 적재 + 수식 23종 테스트 통과 + 셀 단위 계보 추적 |
| M2 — 지식·Agent 기반 | 3, 4 | 근거 3범주 검색·원문 추적 + Critic 5종 검증 + 미참조 숫자 100% 차단 |
| M3 — 시나리오 B | 5 | 신용리스크관리부 백엔드: 부도율 추이·6B 의견·포용금융 비중·HTML 보고서·동적 탭·보고서 변환·진행사업 상태 |
| M4 — 시나리오 A | 6 | 종합기획부 백엔드: 제약 검증·수익성·괴리 탐지·목표 제안·확정·전파 |
| M5 — 화면 완성 | 7 | 시나리오 A/B 화면 완주 |
| M6 — 프로덕션 준비 | 8 | 골든셋·E2E·성능·보안·관측성·복구 리허설 |
| M7 — 확장 | 9 | 도메인 확장 리허설 + SHOULD 기능 + 실데이터 전환 |
