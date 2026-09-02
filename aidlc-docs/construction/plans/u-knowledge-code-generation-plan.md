# Code Generation Plan — U-KNOWLEDGE

이 파일이 Code Generation의 유일한 실행 기준이다. **계획 승인 전에는 제품 코드를 만들지 않는다.**

Infrastructure Design은 SKIP (NFR-1.1, NFR-6.5, P9 A). 로컬 compose·`.env.example`만 Deployment Artifacts 단계에서 둔다.

방법론 기본 경로 `src/{unit-name}/`는 쓰지 않는다 (FR-10, `unit-of-work.md`).

이 파일의 `[Answer]:` G1–G5를 모두 채운 뒤, 채팅에서 **계획을 승인**하거나 **답을 채웠으니 다시 읽고 진행해 달라**고 해 주세요.

---

## Unit Context

- **Workspace Root**: `c:\Users\gogom\cursor-projects\ax-frontier`
- **Project Type**: Greenfield monolith packages (`apps/web` + `apps/api`)
- **Stories (주)**: US-C-01, US-AUX-04, US-AUX-05
- **Dependencies**: 선행 단위 없음. GoalAgent·AttentionAgent·Shell은 이후 단위. 이 단위는 그 단위가 호출할 `listRelated`·`getEvidence`·정책 시드를 연다
- **Entities**: PolicyDocument, DecisionDocument, Article, OfficialDomain, EvidenceRef, DocumentVersion
- **Services**: KnowledgeCommandService, KnowledgeQueryService
- **Code**: `apps/web/src`, `apps/api/src/knowledge`, `apps/api/src/extraction`
- **Docs (markdown only)**: `aidlc-docs/construction/u-knowledge/code/`
- **Never**: `aidlc-docs/`에 ts/tsx, `aidlc-workflows/`에 제품 코드

---

## 이미 고정된 것

- Vite React + Fastify + TypeScript, npm workspaces, Prisma, i18next, Vitest+fast-check
- PostgreSQL compose 기본, `DATABASE_URL` 교체 가능
- `KNOWLEDGE_FILES_DIR` 기본 `data/knowledge`. gitignore
- temp-then-commit, 검색 재시도 없음, 호스트 병렬, 회로차단기 없음
- 파일 20MB, 추출 30초, 검색 호스트 10초·전체 30초
- summary 초기 500자, 저장 4000자
- 인증 없음. `/api` 프록시
- 시드: 여신 정책 요약 PolicyDocument, 포용금융 DecisionDocument, 확정 Article, 도메인 3곳
- 기본 OfficialDomain host: `fsc.go.kr`, `fss.or.kr`, `moef.go.kr` (허용 판정은 해당 host 또는 `*.host`)
- 사업부문 코드 (FR-4.1): `loan` 여신, `deposit` 수신, `pension` 퇴직연금, `wealth` 자산관리, `trust` 신탁, `fx` 외환, `card` 카드
- `data-testid`: `{component}-{element-role}` (NFR-4.2)

---

## Stories

- [ ] US-C-01 원문 확인 (EvidencePanel + getEvidence)
- [ ] US-AUX-04 두 카드, 업로드, HWP/PDF/txt 추출, 메타, 다운로드
- [ ] US-AUX-05 공식 검색, 후보, 확정/해제, 도메인 관리, 시드 확정 기사

---

## 답변에서 확정한 생성 규칙

원문 G1–G5는 모두 “추천안”.

- G1 A: Brave Search API. `OFFICIAL_SEARCH_API_KEY`. URL 재검증
- G2 A: `pdf-parse`
- G3 A: `HWP_EXTRACT_CMD` 필수. 미설정이면 사용자 HWP 실패. README에 LibreOffice 예시
- G4 A: web 5173, api 3001, postgres 5432
- G5 A: Knowledge 라우트만. `/` = 홈. Shell 없음

HTTP 계약 (Step 11):

| 용도 | 경로 |
|---|---|
| 정책 | `GET/POST /api/knowledge/policies`, `GET /api/knowledge/policies/:id`, `PATCH /api/knowledge/policies/:id/summary`, `POST /api/knowledge/policies/:id/versions`, `GET /api/knowledge/policies/:id/file` |
| 의사결정 | 동일, `/decisions` |
| 원문 | `GET /api/knowledge/evidence/:kind/:targetId` |
| 관련 | `GET /api/knowledge/related?sector=&tags=` |
| 검색 | `GET /api/knowledge/search?q=` |
| 검색→후보 | `POST /api/knowledge/search/candidates` |
| 기사 | `GET /api/knowledge/articles`, `POST /api/knowledge/articles`, `POST .../confirm`, `POST .../unconfirm` |
| 도메인 | `GET/POST /api/knowledge/domains`, `DELETE /api/knowledge/domains/:id` |

---

## 생성 전에 고를 것 (G1–G5)

NFR이 코드 생성으로 넘긴 구현체. 생성 단계는 이 답을 따른다.

### Question G1

공식 검색 HTTP 구현체는요? (N3 A)

A) Brave Search API. `site:{host}` + 질의. 키 `OFFICIAL_SEARCH_API_KEY`. 응답 URL 재검증

B) Google Programmable Search JSON API. 같은 키 env. `site` 제한 + URL 재검증

C) Bing Web Search API v7. 같은 키 env. `site:` + URL 재검증

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 키 하나. `site:` 제한. CSE의 cx(B)나 Bing(C)보다 설정이 적다.

---

### Question G2

PDF 텍스트 추출 라이브러리는요? (N4 C)

A) `pdf-parse`

B) `pdfjs-dist`로 텍스트만 추출

C) `unpdf`

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. Node에서 버퍼→텍스트. pdfjs(B)는 DOM/워커 설정이 더 있다.

---

### Question G3

HWP CLI 기본은요? (N4 C, `HWP_EXTRACT_CMD`)

A) env 필수. 미설정이면 사용자 HWP 업로드 실패. README에 LibreOffice 예시만 (`soffice --headless --convert-to txt`)

B) 미설정 시 PATH의 `hwp5txt`를 기본으로 시도. 없으면 실패

C) 미설정 시 `soffice`를 기본으로 시도. 없으면 실패

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. tech-stack: `HWP_EXTRACT_CMD` 미설정이면 사용자 HWP 실패. PATH 기본값(B/C)은 숨은 의존이다.

---

### Question G4

로컬 포트는요?

A) web `5173`, api `3001`, postgres `5432`. Vite `/api` → `http://127.0.0.1:3001`

B) web `5173`, api `3000`, postgres `5432`. Vite `/api` → `http://127.0.0.1:3000`

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. Vite 5173. API 3001은 3000 충돌을 피한다. Postgres 5432.

---

### Question G5

이 단위 Web 진입은요? (Shell은 U-MONITOR)

A) 라우트는 Knowledge만. `/` = Knowledge 홈(카드 2개). 로그인·Nav·locale 전환 컨트롤 없음 (문자열은 i18n 키, locale 기본 `ko`)

B) G5 A와 같되, 상단에 Knowledge 홈으로만 가는 텍스트 링크(임시). 로그인은 없음

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. Shell은 U-MONITOR. 임시 링크(B)는 이 단위에 두지 않는다.

---

## 승인 후 실행할 단계

각 단계는 생성 시 계획 체크박스를 `[x]`로 바꾼다. 제품 코드는 워크스페이스 루트. 요약 md만 `aidlc-docs/construction/u-knowledge/code/`.

- [ ] Step 1: Project Structure Setup — 루트 `package.json` workspaces, `apps/web`, `apps/api`, TypeScript, Vite, Fastify 엔트리, `apps/api/prisma`, `.gitignore`에 `data/`
- [ ] Step 2: Business Logic Generation — 순수 모듈: 허용 호스트, listRelated 필터, EvidenceRef, summary 자르기, 경로 `KNOWLEDGE_FILES_DIR` 하위 여부, 확장자 화이트리스트, 20MB, 도메인 중복
- [ ] Step 3: Business Logic Unit Testing — Vitest 예제 + fast-check (NFR Testable properties)
- [ ] Step 4: Business Logic Summary — `aidlc-docs/construction/u-knowledge/code/business-logic.md`
- [ ] Step 5: Database Migration Scripts — Prisma 모델(Policy, Decision, Article, OfficialDomain, Version). migrate
- [ ] Step 6: Repository Layer Generation — KnowledgeRepository (Prisma)
- [ ] Step 7: Repository Layer Unit Testing
- [ ] Step 8: Repository Layer Summary — `aidlc-docs/construction/u-knowledge/code/repository.md`
- [ ] Step 9: Extraction + FileStore — G2·G3, temp-then-commit, 30초
- [ ] Step 10: OfficialSearchPort — G1, 병렬, URL 재검증, 키 없음=실패
- [ ] Step 11: API Layer Generation — Command/Query, Fastify 라우트, RequestLog, multipart 20MB, 프록시와 맞는 prefix `/api`
- [ ] Step 12: API Layer Unit Testing
- [ ] Step 13: API Layer Summary — `aidlc-docs/construction/u-knowledge/code/api.md`
- [ ] Step 14: Frontend Components Generation — KnowledgeHome, Policy/Decision pages, EvidencePanel, i18n, `data-testid`, G5
- [ ] Step 15: Frontend Components Unit Testing
- [ ] Step 16: Frontend Components Summary — `aidlc-docs/construction/u-knowledge/code/frontend.md`
- [ ] Step 17: KnowledgeSeedRunner — 시드 3종+도메인. 추출 텍스트 동봉. 바이너리 git 없음
- [ ] Step 18: Documentation Generation — `apps/api`·`apps/web` README (실행, env, HWP, 시드)
- [ ] Step 19: Deployment Artifacts — `docker-compose.yml`(Postgres+볼륨), `.env.example`. CI/클라우드 없음 (P9 A)

**Total**: 19 steps.

---

## HTTP (이 단위)

브라우저 origin만. 인증 헤더 없음.

| 용도 | 메서드·경로 (구현 시 이 계약을 연다) |
|---|---|
| 정책 목록/상세 | GET |
| 정책 업로드 | POST multipart |
| 의사결정 목록/상세·업로드 | 동일 |
| summary 수정 | PATCH |
| 원본 다운로드 | GET |
| getEvidence | GET |
| listRelated | GET query: sector, tags |
| searchOfficial | GET query: q |
| 기사 후보·확정/해제·직접 등록 | GET/POST |
| 도메인 목록·추가·삭제 | GET/POST/DELETE |

정확한 경로 문자열은 Step 11에서 `apps/api` 라우트 모듈과 `apps/web` fetch가 같게 맞춘다.

---

## PBT (Step 3에서 구현)

NFR-requirements Testable properties 전부. 생성기는 도메인 값(호스트, sector, tag, EvidenceRef).

---

## 하지 않음 (이 단위)

- Identity, Metrics, Agent, Goals, Admin UI
- OpenAI
- 브라우저 HWP 뷰어
- LLM 요약
- GitHub Actions
- `src/u-knowledge/`
