# NFR Requirements Plan — U-KNOWLEDGE

Construction. Functional Design 승인됨.  
스토리: US-C-01, US-AUX-04, US-AUX-05.  
산출물은 답을 검증한 뒤에만 만든다. 위치: `aidlc-docs/construction/u-knowledge/nfr-requirements/`

이 파일의 `[Answer]:`를 모두 채운 뒤 채팅에서 **답을 채웠으니 다시 읽고 진행해 달라**고 해 주세요.

이 단계에서 고른 웹·API 스택은 이후 단위(U-MONITOR, U-SET-DIRECTION, U-PROPAGATE)의 기본이다. Infrastructure Design은 SKIP이다.

---

## 이미 고정된 것 (다시 묻지 않음)

- 로컬 개발 서버만. 클라우드 없음 (NFR-1.1). 가용성 % 없음 (NFR-6.2)
- 패키지: `apps/web`, `apps/api`. 브라우저는 API만 HTTP (NFR-1.2는 프레임워크만 남음)
- 정형 데이터: PostgreSQL (NFR-2.1). 원본 파일: 로컬 파일, DB는 경로+추출 텍스트 (NFR-2.2 구체 방식만 남음)
- Agent LLM: OpenAI. **이 단위는 LLM 요약 없음** (K4 B)
- 한/영, 기본 한국어 (NFR-4.1). `data-testid`는 코드 생성 (NFR-4.2)
- PBT 전면 (NFR-5). Security extension 미적용 (NFR-7.1). 비밀은 env, 커밋 금지 (NFR-7.2)
- RTO: 로컬 재기동. RPO: 로컬 디스크. 시드 재적재 (NFR-6.3)
- 검색 실패는 숨기지 않음. 추출 실패는 업로드 전체 실패 (K6 A, NFR-6.4)
- HWP 브라우저 뷰어 없음. 추출+다운로드 (FR-7.3)

---

## 답변에서 확정한 생성 규칙

원문 N1–N14는 모두 “추천안”. 요구사항·Functional Design·이미 받은 답과 맞춰 아래 글자로 기록한다.

- N1 A: Vite React SPA + Fastify (TypeScript). 이후 단위의 기본. HWP는 CLI
- N2 C: `KNOWLEDGE_FILES_DIR`, 기본 `data/knowledge/...`. gitignore
- N3 A: 허용 호스트로 제한한 웹 검색 API. 키 없거나 실패면 빈 목록+실패 표시. 제공자 상품명은 코드 생성에서 모듈 하나로 고정
- N4 C: 텍스트·PDF는 라이브러리. 시드 HWP는 추출 텍스트 동봉. 사용자 HWP는 CLI (N1 A)
- N5 A: 파일 20MB, 추출 30초, 검색 전체 30초(호스트당 10초)
- N6 A: 동시 1명, 문서·기사 수십 건, listRelated 스캔
- N7 C: docker compose PostgreSQL이 기본. `DATABASE_URL`만 바꾸면 compose 없이 접속 가능
- N8 A: 이 단위 인증 없음. 확장자·크기·경로 이탈만 막음. Mock 세션은 MONITOR
- N9 A: Web이 `/api`를 API로 프록시. 브라우저는 웹 origin만
- N10 A: Knowledge 문자열 i18n 키. 전환 UI는 Shell
- N11 A: API Vitest+fast-check. Web 예제 테스트
- N12 A: 업로드 중 스피너. 진행률 % 없음
- N13 A: summary 초기 500자, 저장 상한 4000자
- N14 A: Prisma + 마이그레이션. 이 단위가 Knowledge 테이블을 연다

## 승인 후 실행할 체크리스트

- [x] `aidlc-docs/construction/u-knowledge/nfr-requirements/nfr-requirements.md`
- [x] `aidlc-docs/construction/u-knowledge/nfr-requirements/tech-stack-decisions.md`

---

## Question N1

웹과 API 기술 스택은요? (Tech Stack / Maintainability / NFR-1.2)

이 선택이 모노레포 전체의 기본이 된다. `apps/web`과 `apps/api`는 별도 프로세스다.

A) Web: React SPA (Vite, TypeScript). API: Node.js TypeScript (Fastify). HWP 추출은 API가 호출하는 로컬 CLI (없으면 추출 실패 = 업로드 실패)

B) Web: React SPA (Vite, TypeScript). API: Python (FastAPI). PDF·HWP 추출은 API 프로세스 안 라이브러리. 외부 CLI 없음

C) Web: Next.js (App Router, TypeScript). API: NestJS (TypeScript). HWP는 A와 같이 로컬 CLI. Next Route Handler로 API를 합치지 않는다

D) Web: Next.js (App Router, TypeScript). API: Python (FastAPI). 추출은 B와 같음

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 한 사람 Prototype(U3 A)이라 웹·API를 TypeScript로 맞춘다. Next Route Handler로 API를 합치지 않는다 (FR-10). NestJS+Next(C)는 로컬 Prototype에 비해 무겁다. Python 분리는 이후 Agent 단위까지 언어가 갈린다.

---

## Question N2

업로드 원본 파일의 로컬 저장 방식은요? (NFR-2.2)

A) 워크스페이스 `data/knowledge/{kind}/{documentId}/v{version}/original.{ext}`. DB에는 이 상대 경로. gitignore

B) `apps/api` 아래 `var/files/...` (구조는 A와 같음). DB에는 API 기준 상대 경로. gitignore

C) 환경 변수 `KNOWLEDGE_FILES_DIR`(기본값은 A와 같은 `data/knowledge`). 경로 규칙만 A와 동일

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **C**. 기본 경로는 N8 A가 쓰는 `KNOWLEDGE_FILES_DIR`와 같다. 기본값은 `data/knowledge`. 테스트는 env로 다른 디렉터리를 가리킬 수 있다.

---

## Question N3

공식 도메인 실시간 검색은 기술적으로 어떻게 할까요? (Integration / Reliability / FR-7.8)

히트 URL은 허용 호스트가 아니면 버린다 (K6 A). 검색 실패는 숨기지 않는다.

A) 허용 호스트로 제한한 웹 검색 API(키는 env). 응답 URL을 허용 목록으로 재검증. 키 없거나 호출 실패면 빈 목록+실패 표시

B) 허용 도메인의 공개 목록/RSS/검색 페이지만 HTTP GET. 범용 웹 검색 API 없음. 페이지를 못 읽으면 해당 호스트 실패

C) 로컬에 공식 문서·기사 시드 인덱스를 두고 질의를 그 인덱스에서 찾는다. 실시간 HTTP는 연결 실패 데모용으로만 두고, 기본 경로는 인덱스

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. FR-7.8은 실시간 검색이다. C는 기본이 로컬 인덱스라 실시간과 어긋난다. B는 검색이 아니라 페이지 GET이다. 키 없음·호출 실패는 NFR-6.4대로 숨기지 않는다. 기사 후보는 시드·직접 등록으로도 채운다 (K5 C).

---

## Question N4

PDF·텍스트·HWP 추출 도구는요? (Tech Stack / Reliability / FR-7.3)

추출 실패 = 업로드 실패, 파일 안 남김 (K6 A).

A) 텍스트는 UTF-8 읽기. PDF는 API 언어의 라이브러리. HWP는 로컬 CLI(예: LibreOffice 또는 hwp 텍스트 추출기). 미설치면 추출 실패

B) 세 형식 모두 API 프로세스 안 라이브러리만. 외부 바이너리 없음. 그 라이브러리가 HWP를 못 다루면 업로드 실패

C) 텍스트·PDF는 라이브러리. HWP는 데모 시드에 추출 텍스트를 함께 두고, 사용자가 올린 HWP는 CLI(A)로 추출

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **C**. 시드 재적재(NFR-6.3)가 CLI 설치에 묶이지 않게 시드 HWP는 추출 텍스트를 동봉한다. 사용자가 올린 HWP는 N1 A의 CLI. 미설치·비0 종료는 추출 실패 = 업로드 실패 (K6 A).

---

## Question N5

이 단위의 성능 상한은요? (Performance)

로컬 Prototype이라 p95 SLA·다중 리전은 두지 않는다 (NFR-6.2).

A) 원본 파일 최대 20MB. 추출 제한시간 30초. 공식 검색 전체 30초(호스트당 10초). 초과는 실패

B) 파일 최대 5MB. 추출 10초. 검색 전체 15초(호스트당 5초)

C) 파일·시간 숫자 상한 없음. 끝날 때까지 대기. 디스크·프로세스가 감당하는 범위

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 정책 PDF가 수 MB일 수 있어 5MB(B)는 짧다. 상한 없음(C)은 로컬 디스크를 막지 않는다.

---

## Question N6

부하·용량 가정은요? (Scalability)

A) 동시 사용자 1명(로컬 데모). 문서·기사 합쳐 수십 건. listRelated는 전체 스캔

B) 동시 사용자 최대 5. 문서·기사 수백 건. 인덱스는 두지 않고 스캔

C) 동시 업로드를 직렬화(한 건씩 추출). 조회는 B와 같음

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 로컬 데모·한 작업 흐름(U3 A). 수백 건·업로드 큐는 이 Prototype에 필요 없다.

---

## Question N7

로컬 PostgreSQL은 어떻게 띄울까요? (Tech Stack / NFR-2.1)

A) 워크스페이스 `docker compose`로 PostgreSQL + 로컬 볼륨. 앱 프로세스는 호스트

B) 개발자 머신에 설치한 PostgreSQL. compose 없음

C) 개발·테스트는 PostgreSQL과 같은 스키마를 쓰는 로컬 인스턴스만 (A 또는 B 중 문서에 compose를 기본으로 적고, compose 없이 접속 URL만 바꿔도 됨)

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **C**. compose로 PostgreSQL+볼륨을 기본으로 적는다. 앱은 호스트. `DATABASE_URL`만 바꾸면 설치형 Postgres에도 붙는다.

---

## Question N8

이 단위 Knowledge API의 접근 제어는요? (Security / NFR-7)

Security baseline은 강제하지 않는다. 로그인은 U-MONITOR.

A) 이 단위 API는 인증 없음(로컬). 업로드는 확장자 화이트리스트·크기 상한·저장 경로가 `KNOWLEDGE_FILES_DIR` 밖으로 나가지 않게만 막는다. Mock 세션은 MONITOR에서 붙인다

B) Knowledge 쓰기(업로드·확정·도메인 변경)만 이후 Identity Mock과 같은 가드를 전제한다. 지금은 가드 없이 열고, MONITOR에서 가드를 넣는다. 조회는 계속 인증 없음

C) 이 단위부터 고정 데모 헤더(예: `X-Persona: strategy-planning`)가 없으면 4xx. 키는 env

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 로그인은 U-MONITOR. 이 단위는 확장자 화이트리스트·N5 크기·`KNOWLEDGE_FILES_DIR` 밖 경로 거부만. Security baseline 미적용 (NFR-7.1).

---

## Question N9

브라우저가 API를 치는 로컬 연결은요? (Tech Stack / Usability)

A) Web dev 서버가 `/api`를 `apps/api`로 프록시. 브라우저는 웹 origin만 사용

B) Web과 API가 다른 포트. API는 웹 origin만 CORS 허용

C) 개발은 CORS `*` (로컬만). 배포가 생기면 그때 좁힌다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 브라우저는 `apps/api`만 치되, 개발 중 origin은 웹이다. CORS `*`(C)는 쓰지 않는다.

---

## Question N10

이 단위 화면의 한/영은요? (Usability / NFR-4.1)

A) Knowledge UI 문자열은 i18n 키. 기본 한국어. locale 전환 UI는 Shell(U-MONITOR)이 붙이면 그대로 동작

B) 이 단위는 한국어 문자열만. 영어 전환은 MONITOR에서 Knowledge 문자열을 키로 옮긴다

C) 이 단위부터 화면에 언어 전환을 둔다 (Shell보다 앞섬)

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. NFR-4.1. 전환 UI는 Shell(D3). 이 단위부터 키를 두면 MONITOR에서 문자열을 옮기지 않는다. 화면 전환을 Knowledge에 두면 Shell보다 앞선다 (C 제외).

---

## Question N11

이 단위 PBT·예제 테스트 도구는요? (Maintainability / NFR-5)

대상 속성(코드 생성에서 테스트): 허용 호스트 판정, Article 확정 전후 listRelated·getEvidence, EvidenceRef 직렬화 round-trip, 부문+Tag 교집합 필터.

A) 예제 테스트 + PBT를 API 언어에 맞춤 (TypeScript면 Vitest+fast-check, Python이면 pytest+Hypothesis). Web 컴포넌트는 예제 테스트

B) API만 A. Web은 이 단위에서 자동 테스트 없음 (E2E는 이후)

C) 이 단위는 예제 테스트만. PBT는 Agent가 있는 단위에서 시작한다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. PBT 전면 (NFR-5.1). C는 이 단위 비즈니스 로직(허용 호스트, 확정, listRelated)에 PBT를 빼므로 쓰지 않는다. Knowledge UI가 있으므로 Web 예제 테스트는 둔다 (B 제외).

---

## Question N12

업로드 중 사용자에게 보이는 피드백은요? (Usability)

실패 시 폼 오류, 목록에 안 올라감은 이미 고정 (K6 A).

A) 제출 후 완료/실패까지 대기. 업로드 중 표시(스피너). 진행률 % 없음

B) 파일 전송+추출 진행률을 보여 준다

C) 별도 진행 UI 없음. 응답이 올 때까지 버튼만 비활성

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. 완료까지 동기 대기(K6 A). 진행률은 Functional Design API에 없다. 버튼만 비활성(C)은 추출 30초 동안 상태가 안 보인다.

---

## Question N13

summary 초기값 길이 상한은요? (Performance / 도메인 상수)

추출 텍스트 전체는 저장한다. summary만 상한. 사용자는 수정 가능 (K4 B).

A) 초기값 500자. 사용자가 더 길게 수정 가능. 저장 상한 4000자

B) 초기값 2000자. 저장 상한 4000자

C) 초기값 = 추출 텍스트 전체(상한 없음). 화면만 접기

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. summary 초기값은 추출 앞부분(K4 B). 500자. 저장 상한 4000자. 추출 텍스트 전체는 별도 필드에 둔다.

---

## Question N14

PostgreSQL 접근·마이그레이션은요? (Tech Stack / Maintainability)

A) 언어 기본 ORM + 마이그레이션 (TS: Prisma, Python: SQLAlchemy+Alembic). 이 단위가 Knowledge 테이블을 연다

B) 쿼리 빌더 (TS: Drizzle, Python: SQLAlchemy Core) + SQL 마이그레이션 파일

C) `node-pg` / `psycopg` + SQL 마이그레이션 파일. ORM 없음

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **A**. N1 A가 TypeScript이므로 Prisma. Knowledge 스키마는 이 단위가 연다 (`unit-of-work-dependency.md`).
