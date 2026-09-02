# Application Design Plan

실행 계획 승인 후 Application Design — Planning. 산출물은 답을 검증하고 이 계획을 승인한 뒤에만 만든다.

- 요구사항: `aidlc-docs/inception/requirements/requirements.md`
- 스토리: `aidlc-docs/inception/user-stories/stories.md`
- 코드 위치: `apps/web`, `apps/api` (프레임워크는 Construction NFR)

이 파일의 `[Answer]:`를 모두 채운 뒤 채팅에서 **답을 채웠으니 다시 읽고 진행해 달라**고 해 주세요.

이 단계는 컴포넌트 경계·인터페이스·서비스 오케스트레이션·의존이다. 화면 레이아웃, 프레임워크, 상세 업무 규칙은 여기서 정하지 않는다.

---

## 이미 요구사항에서 고정된 것

- 패키지: `apps/web`, `apps/api`. 제품 코드는 `aidlc-docs/`에 두지 않음
- 저장: PostgreSQL. 업로드 원본은 로컬 파일, DB에는 경로와 추출 텍스트
- LLM: OpenAI API. 확정 목표 숫자는 모델이 만들지 않음. 근거 ID 없이 Agent 완료로 보지 않음
- 로컬만. 클라우드는 없음
- 여신만 LLM Attention. 다른 부문은 고정 Mock
- 확인·보고 생성 UI 없음. 공유 저장소 + 생성 API
- 사업부서 화면 없음. 현재 목표 읽기 모델·API만

---

## 답변에서 확정한 생성 규칙

F1–F3 원문은 추천 위임이다. 요구사항·이미 받은 D답과 맞춰 F1 A, F2 A, F3 B로 기록한다.

- **Web**: Shell(로그인·Nav·한/영), Dashboard UI, Loan Detail UI, Goals UI, Knowledge UI, Admin UI (D1 A 화면 쪽, D3 A)
- **API**: Modular monolith. Identity, Metrics, Attention, ReportRequest, ManagementGoal, Knowledge, Extraction, AttentionAgent, GoalAgent, Admin/Seed. 모듈 사이는 공개 인터페이스만 (D8 A, D9 B, F1 A)
- **화면→API**: Web이 도메인 API를 조합한다. Dashboard = Attention + ReportRequest + Metrics. Loan Detail = Metrics + AttentionAgent(해설). Goals = ManagementGoal Command/Query + GoalAgent. Knowledge UI = Knowledge + Extraction
- **Agent**: AttentionAgent — 여신 Attention 선정, 여신 상세 해설, Dashboard 추가 질문. GoalAgent — 목표 검토, 신규 제안, 목표 화면 추가 질문, 관련 문서 선정 (D2 C, F2 A)
- **근거**: 모든 Agent 응답에 evidenceIds 필수. 빈 목록은 실패 (D4 A). 공유 규칙: Evidence First, 관련 문서만, 근거 ID
- **Knowledge 읽기**: 목표 검토·신규 + Attention의 정책 요약 (F3 B). 여신 상세 해설은 Metrics만 (D7 B)
- **목표 확인**: Goal Command. 전파 읽기: Goal Query (D5 B)
- **통신**: 브라우저는 `apps/api`만 HTTP. OpenAI·공식 검색·파일은 API만. LLM 요청-응답 (D6 A). 공식 검색 클라이언트는 Knowledge
- **확인·보고**: ReportRequest가 생성 API와 목록 조회 (D10 A)

이 규칙으로 `application-design/` 산출물을 만들어도 되면 계획을 **승인**해 주세요.

## 승인 후 실행할 체크리스트

- [x] `aidlc-docs/inception/application-design/components.md`
- [x] `aidlc-docs/inception/application-design/component-methods.md`
- [x] `aidlc-docs/inception/application-design/services.md`
- [x] `aidlc-docs/inception/application-design/component-dependency.md`
- [x] `aidlc-docs/inception/application-design/application-design.md` (위 문서 통합)
- [x] 설계가 스토리·FR과 모순 없는지 대조

---

## Question D1

컴포넌트 경계를 무엇 기준으로 나눌까요? (패키지 `apps/web`·`apps/api`는 유지)

A) 화면·Journey: Web Shell(로그인·Nav·한/영), Dashboard UI, Loan Detail UI, Goals UI, Knowledge UI, Admin UI. API는 그에 대응하는 모듈

B) 도메인: Identity, Attention, ReportRequest, Metrics, ManagementGoal, Knowledge, Evidence, Agent, Admin. Web은 이 API를 조합하는 하나의 UI 앱

C) API는 계층만 (HTTP / 응용 / 저장). 도메인 모듈은 Units Generation에서 자른다. 지금은 Web App + Api App + File Store + OpenAI + Official Search 다섯 덩어리만 적는다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question D2

Agent(LLM 호출)와 업무 유스케이스의 경계는요?

A) Agent 컴포넌트 하나: 여신 Attention 선정, 여신 해설, 기존 목표 검토, 신규 목표 제안, 자연어 추가 질문, 관련 문서 선정을 모두 이 컴포넌트가 한다

B) LLM Gateway만 프롬프트 입출력을 담당한다. Attention·목표 검토·신규 제안·추가는 각각 유스케이스 서비스가 패킷을 만들고 Gateway를 호출한다

C) AttentionAgent와 GoalAgent를 나눈다. 근거 규칙(Evidence First, 관련 문서만, 근거 ID)은 공유한다

X) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Question D3

관리 화면(시드 숫자·목표 변경)과 한/영은 어디에 둘까요?

A) 같은 `apps/web` 안의 Admin 모듈 + i18n은 Shell. API에 Seed/Admin 쓰기 엔드포인트

B) Admin만 별도 라우트 그룹으로 두되 컴포넌트 목록에서는 Dashboard 등과 같은 급으로 적는다

C) Admin은 보조 스토리이므로 설계 문서에는 Shell의 일부로만 짧게 적고, 독립 컴포넌트는 만들지 않는다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question D4

Agent가 내는 결과의 인터페이스에서 근거는 어떻게 강제할까요? (NFR-3.3: 근거 ID 없으면 완료 아님)

A) 모든 Agent 응답 타입에 evidenceIds(또는 동등)가 필수다. 빈 목록이면 API가 실패로 처리하고 화면에 제안/Attention을 완료로 보여 주지 않는다

B) 유스케이스가 응답을 받은 뒤 Evidence 컴포넌트에 검증을 맡긴다. Gateway는 문자열만 반환한다

C) 여신 Attention·목표 수정·신규 제안에만 근거 ID를 필수. 여신 지표 해설 요약은 비교 숫자 참조만으로 충분하다

X) Other (please describe after [Answer]: tag below)

[Answer]: A 

---

## Question D5

경영목표 확인(유지 / 제안 그대로 / 일부 수정 후 반영, 신규 추가)을 누가 오케스트레이션할까요?

A) Goal Application Service 하나: 현재 목표 저장, History, 생성방식, 상태, 이후 사업부서용 읽기 모델을 같은 유스케이스에서 끝낸다. Agent는 제안만 만든다

B) Goal Command 서비스와 Goal Query(전파 읽기) 서비스를 나눈다. 확인은 Command, US-D-01 읽기는 Query

C) Persistence가 확인 시 한 트랜잭션으로 처리하고, 응용 서비스는 얇게만 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question D6

Web과 API, API와 외부(OpenAI·공식 도메인)의 통신은요?

A) 브라우저는 HTTP로 `apps/api`만 호출한다. OpenAI·공식 도메인 검색·파일 시스템은 API만 접근한다. LLM은 요청-응답(사용자가 기다림)

B) 브라우저는 HTTP로 `apps/api`만 호출한다. LLM이 긴 경우 API는 작업 ID를 주고 Web이 폴링한다 (로컬 큐)

C) A와 같되, 공식 도메인 검색만 브라우저가 직접 하지 않는다는 점까지 설계 문서에 명시하고, 검색 클라이언트는 Knowledge 모듈 안에 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question D7

Knowledge(문서·HWP 추출·기사 확정·공식 검색)를 누가 쓰나요?

A) Agent/유스케이스만 읽는다. Dashboard 해설도 목표 검토와 같은 Knowledge 조회 API를 쓴다

B) Knowledge는 목표 검토·신규 제안에만 쓰인다. 여신 상세 해설은 Metrics만 본다

C) Knowledge 쓰기는 Admin/업로드 UI와 기사 확정만. 읽기는 Agent 전용 내부 API이고 Web은 근거 원문 열기(다운로드·추출 텍스트)만 호출한다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question D8

`apps/api` 안의 구조 패턴은요? (프레임워크 이름은 Construction에서)

A) Modular monolith: Identity, Metrics, Attention, ReportRequest, ManagementGoal, Knowledge, Agent(또는 Gateway) 모듈. 모듈 사이는 공개 인터페이스만

B) 3계층(HTTP-응용-저장)만. 테이블/유스케이스는 계층 안에서 나눈다

C) Hexagonal: 포트로 PostgreSQL, 파일, OpenAI, 공식 HTTP 검색을 바꾸고, 도메인 로직은 어댑터 밖에 둔다

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Question D9

HWP/PDF 텍스트 추출은 어느 컴포넌트 메서드로 둘까요?

A) Knowledge(Document) 컴포넌트 메서드: 업로드 → 저장 경로 → 추출 텍스트 → 메타. Agent는 추출 텍스트만 읽는다

B) 별도 Extraction 컴포넌트. Knowledge는 메타와 파일 경로만 들고 Extraction을 호출한다

C) 업로드 시 추출은 Knowledge, Agent가 근거로 쓸 때 한 번 더 추출한다

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Question D10

확인·보고 요청 생성 API(UI 없음)는 어느 컴포넌트에 둘까요?

A) ReportRequest 컴포넌트: 생성 API + 목록 조회. Dashboard UI는 목록 조회만 쓴다

B) Dashboard 모듈이 목록을 갖고, 생성 API만 별도 Propagation/Inbound 컴포넌트에 둔다

C) Identity/Persona 모듈이 생성 주체를 검증하고, 저장은 ReportRequest가 한다. 목록은 Dashboard 서비스가 ReportRequest를 읽는다

X) Other (please describe after [Answer]: tag below)

[Answer]: A
