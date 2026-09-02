# Unit of Work Plan

Application Design 승인 후 Units Generation — Planning. 단위 산출물은 답을 검증하고 이 계획을 승인한 뒤에만 만든다.

- 요구사항: `apps/web`, `apps/api` 모노레포. 로컬만
- 설계: Web은 화면 모듈, API는 도메인 모듈러 모노리스
- 스토리 16개: `aidlc-docs/inception/user-stories/stories.md`

단위(Unit of Work)는 Construction에서 Functional Design을 반복하는 개발 묶음이다. 독립 배포 서비스면 Service, 패키지 안 논리 묶음은 Module.

이 파일의 `[Answer]:`를 모두 채운 뒤 채팅에서 **답을 채웠으니 다시 읽고 진행해 달라**고 해 주세요.

---

## 이미 고정된 것

- 제품 코드 위치: 워크스페이스 루트 `apps/web`, `apps/api`. `aidlc-docs/`에 제품 코드 없음
- 브라우저는 API만 호출. OpenAI·검색·파일은 API만
- Infrastructure Design SKIP. 클라우드 없음
- 한 사람/한 저장소 Prototype (팀 규모는 아래 U3에서 확인)

---

## 답변에서 확정한 생성 규칙

F1 원문: “추천안”. U1·U5는 여정·제품 루프로 묶고, U4 C의 “한 프로세스에 같이 둔다”는 배포 이야기이므로 **F1 B (4단위)** 로 기록한다. 5단위는 Journey A를 두 번 Functional Design 하게 되고, 1단위는 U1·U5를 버린다.

- **U-MONITOR**: 진입, 은행 Dashboard, 여신 상세. 화면+해당 API를 같이 (U2 B)
- **U-SET-DIRECTION**: 경영목표 설정 (검토·제안·확인·신규)
- **U-KNOWLEDGE**: 정부정책·의사결정 DB, HWP/추출, 공식 검색, 기사 확정, 근거 원문
- **U-PROPAGATE**: 현재 목표 읽기 API, 확인·보고 생성 API, 시드 관리 화면

공통:

- 소유: 한 작업 흐름 (U3 A)
- 경로: `apps/web`, `apps/api`만 (U6 B, FR-10)
- API 안 도메인은 Application Design 모듈 이름 유지
- 스토리마다 그 단위의 Web과 API를 같이 연다 (U2 B)
- Construction 순서: **U-KNOWLEDGE → U-MONITOR → U-SET-DIRECTION → U-PROPAGATE**. Attention·GoalAgent가 문서를 읽으므로 스키마·시드·등록 UI는 U-KNOWLEDGE가 먼저다.

이 규칙으로 `unit-of-work.md` / `unit-of-work-dependency.md` / `unit-of-work-story-map.md`를 만들어도 되면 계획을 **승인**해 주세요.

## 승인 후 실행할 체크리스트

- [x] `aidlc-docs/inception/application-design/unit-of-work.md` (정의·책임, greenfield 코드 배치)
- [x] `aidlc-docs/inception/application-design/unit-of-work-dependency.md`
- [x] `aidlc-docs/inception/application-design/unit-of-work-story-map.md` (스토리 16개 전부 배정)
- [x] 단위 경계·의존 검증
- [x] 스토리 누락 없는지 대조

---

## Question U1

스토리를 어떤 단위로 묶을까요? (Story Grouping)

A) 패키지 2개: **U-WEB** (모든 UI 스토리), **U-API** (저장·Agent·API). 한 스토리가 화면+API면 둘 다에 올리고, 구현 순서는 API 계약을 먼저 한다

B) Journey 단위: 진입+Dashboard, 여신 상세, 경영목표, Knowledge, 전파·시드. 각 단위에 그 화면과 필요한 API를 같이 넣는다

C) 3개: **U-WEB**, **U-API-CORE** (Identity, Metrics, Goal, ReportRequest, Admin), **U-API-AGENT** (AttentionAgent, GoalAgent, Knowledge, Extraction)

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question U2

단위 사이 의존과 통합은요? (Dependencies)

A) U-API가 계약(HTTP)을 먼저 열고, U-WEB은 그 계약만 사용한다. Agent는 API 단위 내부 의존이다

B) 스토리 단위로 Web·API를 같은 스프린트에서 같이 연다. 계약은 스토리마다 확장한다

C) `apps/shared`에 타입·EvidenceId를 두고 Web과 API가 같이 의존한다. 공유 패키지가 세 번째 단위다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question U3

누가 단위를 소유하나요? (Team Alignment)

A) 한 팀(또는 한 작업 흐름)이 모든 단위를 순서대로 한다. 소유 구분은 문서상의 단위일 뿐

B) Web과 API를 다른 사람이 맡을 수 있게 단위를 나누고, 계약만 맞춤

C) Agent/Knowledge만 따로 소유할 수 있게 C안(U1 C)에 맞춘다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question U4

배포·확장 차이가 단위를 가르나요? (Technical Considerations)

A) 차이 없음. 로컬에서 web 프로세스 + api 프로세스 + PostgreSQL. 단위는 개발 묶음이지 별도 스케일 단위가 아니다

B) Agent(OpenAI)만 나중에 분리할 수 있게 U-API-AGENT를 독립 단위로 둔다. 이번엔 같은 `apps/api` 프로세스에 넣되 단위 문서는 분리한다

C) 지금은 한 단위(모노레포 전체). 패키지 둘은 모듈일 뿐 Units Generation에서 쪼개지 않는다

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question U5

업무 도메인 경계와 단위의 관계는요? (Business Domain)

A) 단위는 패키지(Web/API)다. 도메인(Identity, Metrics, Goal, Knowledge, Agent)은 **U-API 안의 모듈**이다. Application Design 모듈 이름을 유지한다

B) 단위를 MONITOR / SET DIRECTION / Knowledge / PROPAGATE에 맞춘다. 패키지는 그 안의 코드 위치일 뿐

C) 도메인마다 단위 하나 (Identity 단위, Goal 단위, …). Construction Functional Design을 도메인마다 반복한다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question U6

코드 디렉터리는요? (Code Organization — greenfield, FR-10과 방법론 패턴)

방법론 기본 패턴은 단일 단위면 루트 `src/`, 멀티 단위 모노리스면 `src/{unit-name}/`이다. 이 프로젝트 요구사항은 **`apps/web`, `apps/api`** 다.

A) FR-10을 유지한다. 단위가 2개면 `apps/web/src`, `apps/api/src` (및 각 `tests/`). API 안 도메인 모듈은 `apps/api/src/{module}`

B) 단위를 Journey/도메인 여러 개로 두되, 물리 경로는 그대로 `apps/web`, `apps/api`만 쓴다. `src/{unit-name}/` 루트 패턴은 쓰지 않는다

C) 방법론 패턴대로 워크스페이스 루트에 `src/web`, `src/api`를 둔다. FR-10의 `apps/web`·`apps/api`는 이 선택으로 바꾼다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안

기록된 선택: **B**. 물리 경로는 `apps/web`, `apps/api`만 쓴다. FR-10을 바꾸지 않는다.
