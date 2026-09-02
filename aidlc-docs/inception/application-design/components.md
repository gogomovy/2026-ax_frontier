# Components

계획: `aidlc-docs/inception/plans/application-design-plan.md`  
패키지: `apps/web`, `apps/api`. 프레임워크는 Construction NFR.

모듈 사이는 공개 인터페이스만 호출한다. 브라우저는 `apps/api`만 HTTP로 호출한다.

---

## Web (`apps/web`)

### WebShell
- **목적**: Mock 로그인, Persona별 진입, 상위 Navigation, 한/영
- **책임**: 세 계정 로그인. 종합기획부는 Dashboard로, 나머지 Persona는 ‘이후 구현’. 은행 Dashboard / 경영목표 설정 / 데이터베이스 이동. locale 기본 한국어
- **인터페이스**: Identity HTTP, i18n 리소스
- **스토리**: US-LOGIN-01, US-LOGIN-02, US-AUX-01, FR-3.1

### DashboardUi
- **목적**: 은행 메인 Dashboard
- **책임**: 사업부문 카드, 부문별 Attention 요약 목록, 확인·보고 목록. Attention과 보고를 구분. 여신 카드만 상세로 이동. 검토 대상으로 등록
- **인터페이스**: Attention, ReportRequest, Metrics HTTP
- **스토리**: US-A-01, US-A-02, US-A-03(진입), US-A-05

### LoanDetailUi
- **목적**: 여신 상세
- **책임**: 상위 Attention·근거 재표시. 종합수익·기업여신·가계여신(포용금융 지표 포함)과 Agent 해설. 검토 대상 등록
- **인터페이스**: Metrics, Attention, AttentionAgent HTTP
- **스토리**: US-A-03, US-A-04, US-A-05

### GoalsUi
- **목적**: 여신 경영목표 설정
- **책임**: 사업부문 카드에서 여신만 설정 화면. 현재 목표 List, 검토 필요사항, Agent 수정·신규 제안, 유지/반영/수정 후 반영, 신규 추가, 근거 원문 열기 진입
- **인터페이스**: ManagementGoal Command/Query, GoalAgent, Knowledge(원문) HTTP
- **스토리**: US-B-01~04, US-C-01

### KnowledgeUi
- **목적**: 정부정책·경영 의사결정 DB, 기사 확정
- **책임**: 두 카드. 업로드, 메타, 추출 텍스트/요약 확인, 원본 다운로드. 공식 검색 결과 후보, 기사 확정
- **인터페이스**: Knowledge, Extraction HTTP
- **스토리**: US-AUX-04, US-AUX-05, US-C-01(원문)

### AdminUi
- **목적**: 데모 시드 숫자·목표 변경
- **책임**: 관리 화면에서 실적·목표를 바꿔 다른 시나리오를 보여 줌
- **인터페이스**: AdminSeed HTTP
- **스토리**: US-AUX-02

---

## API (`apps/api`)

### Identity
- **목적**: Persona·세션
- **책임**: Mock 로그인. Persona를 데이터와 라우팅 힌트로 남김. SSO 없음
- **인터페이스**: 로그인 요청 → 세션/Persona, 진입 경로
- **스토리**: US-LOGIN-*

### Metrics
- **목적**: 당행 정형 실적
- **책임**: 사업부문 카드용 요약. 여신 종합수익·기업·가계 비교값(현재, 전년 동분기, 증감액, 증감률). 포용금융 지표. 시드 교체 가능
- **인터페이스**: 조회. AdminSeed가 갱신
- **스토리**: US-A-01, US-A-04, US-B-02(당행 현황 근거)

### Attention
- **목적**: Attention 목록 저장·조회
- **책임**: 메인 notification list. 부문별 1~2개. 여신은 AttentionAgent 결과 저장. 비여신은 고정 Mock, LLM 호출 없음. 상세에서 동일 Attention·근거 재조회
- **인터페이스**: listForDashboard, getForSector, persistLoanAttentions
- **스토리**: US-A-01, US-A-03

### ReportRequest
- **목적**: 확인·보고 요청 공유 저장소
- **책임**: 생성 API(UI 없음)와 목록 조회. 시드와 API 생성이 같은 레코드
- **인터페이스**: create, list
- **스토리**: US-A-02, US-D-02

### ManagementGoal
- **목적**: 여신 경영목표와 검토 대상, History
- **책임**: 현재 목표 List, 상태, 확인(유지/반영/수정 후 반영, 신규 그대로/수정 후/직접). History. 검토 필요사항. 이후 사업부서용 현재 목표 읽기 모델. 확정 숫자는 사용자
- **인터페이스**: Command(쓰기), Query(전파 읽기, 목록)
- **스토리**: US-A-05, US-B-*, US-D-01

### Knowledge
- **목적**: 정책·의사결정 문서, 기사 확정, 공식 도메인 검색
- **책임**: 메타, 파일 경로, 추출 텍스트 보관. 업로드 시 Extraction 호출. 공식 도메인만 검색. 기사 후보는 확정 후에만 근거. Agent에는 관련 문서만 조회 API 제공
- **인터페이스**: 등록/조회/확정/검색/원문. Official search 클라이언트는 이 모듈 안
- **스토리**: US-C-01, US-AUX-04, US-AUX-05, US-B-02, US-B-04

### Extraction
- **목적**: 파일 텍스트 추출
- **책임**: HWP·PDF·텍스트 추출. 원본은 로컬 파일. Knowledge가 경로를 넘기고 텍스트를 받음. 브라우저 HWP 뷰어 없음
- **인터페이스**: extract(path, type) → text
- **스토리**: US-AUX-04

### AttentionAgent
- **목적**: 여신 Attention, 여신 상세 해설, Dashboard·여신 맥락 추가 질문
- **책임**: 여신 Attention은 Metrics·현재 목표·Knowledge 정책 요약을 읽고 고른다. 상세 해설은 Metrics만. 모든 응답에 evidenceIds. 빈 목록은 실패. 인과 단정 금지
- **인터페이스**: selectLoanAttentions, commentLoan, answerFollowUp
- **스토리**: US-A-01, US-A-04, US-AUX-03

### GoalAgent
- **목적**: 기존 목표 검토, 신규 제안, 목표 화면 추가 질문, 관련 문서 선정
- **책임**: 세 근거. 방향+범위, 확정 숫자 금지. 관련 문서만. 포용금융 신규는 가계 포용금융 지표 + 확정 기사 + 내부 논의 + 공식 정책. 모든 응답에 evidenceIds
- **인터페이스**: reviewGoals, proposeNew, selectRelatedDocuments, answerFollowUp
- **스토리**: US-B-02, US-B-04, US-AUX-03, FR-7.6

### AdminSeed
- **목적**: 데모 시드 변경
- **책임**: Metrics·목표 숫자 갱신. 기업여신 하회, 가계 관리목표 근접, 포용금융 시나리오 재현
- **인터페이스**: updateMetrics, updateGoals
- **스토리**: US-AUX-02, FR-9

---

## 공유 계약 (별도 컴포넌트 아님)

- **AgentResult**: 본문 + 필수 evidenceIds. 빈 목록이면 API가 실패
- **Evidence 구분**: 당행 Data / 내부 경영방향 / 외부 정책(공식) / 확정 기사
- **OpenAI**: AttentionAgent·GoalAgent만 호출. 브라우저·다른 모듈은 호출하지 않음
