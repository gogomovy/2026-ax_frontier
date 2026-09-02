# Application Design Plan — 추가 질문

D1–D10을 모두 읽었습니다. 선택 글자는 비어 있지 않습니다. 아래는 서로 다른 답을 한 문서에서 쓰려면 규칙이 필요한 항목입니다.

`[Answer]:` 뒤에 선택 글자를 적어 주세요. 채운 뒤 채팅에서 다시 읽어 달라고 해 주세요.

---

## 이미 확정으로 받아들인 답

- D2 C: AttentionAgent와 GoalAgent를 나눈다. Evidence First·관련 문서만·근거 ID는 공유한다
- D3 A: `apps/web` Admin 모듈. i18n은 Shell. API에 Seed/Admin 쓰기
- D4 A: Agent 응답에 evidenceIds 필수. 빈 목록은 실패, 화면에서 완료로 보여 주지 않음
- D5 B: Goal Command(확인)와 Goal Query(전파 읽기)를 나눈다
- D6 A: 브라우저는 `apps/api`만 HTTP 호출. OpenAI·검색·파일은 API만. LLM은 요청-응답
- D7 B: Knowledge는 목표 검토·신규 제안에만. 여신 상세 해설은 Metrics만
- D9 B: Extraction 컴포넌트 별도. Knowledge는 메타·경로, 추출은 Extraction 호출
- D10 A: ReportRequest가 생성 API와 목록 조회를 모두 갖는다

---

## Question F1

D1은 API를 **화면(Journey)에 대응하는 모듈**로 두라고 했고, D8은 API를 **도메인 모듈**(Identity, Metrics, Attention, ReportRequest, ManagementGoal, Knowledge, Agent)로 두라고 했습니다. 둘을 어떻게 합칠까요?

A) Web만 D1(화면 모듈). API는 D8 도메인 모듈. Dashboard 화면은 Attention·ReportRequest·Metrics API를 조합한다. D1의 “API도 화면 모듈”은 쓰지 않는다

B) Web과 API 모두 화면 모듈(Dashboard API, Goals API 등). D8 도메인 이름은 그 모듈 안의 패키지 이름일 뿐

C) Web은 D1. API는 D8 도메인이되, 화면마다 얇은 BFF 응용 서비스가 여러 도메인을 오케스트레이션한다

X) Other (please describe after [Answer]: tag below)

[Answer]: 너의 추천안으로 해줘

기록된 선택: **A**. Web은 화면 모듈(D1). API는 도메인 모듈(D8). Dashboard는 Attention·ReportRequest·Metrics를 조합한다.

---

## Question F2

D2는 Agent를 AttentionAgent / GoalAgent로만 나눴습니다. 여신 상세 해설(US-A-04), 자연어 추가 질문(US-AUX-03), 관련 문서 선정(FR-7.6)은 어디에 둘까요?

A) 여신 Attention 선정·여신 상세 해설·Dashboard 기준 추가 질문은 AttentionAgent. 목표 검토·신규 제안·목표 화면 추가 질문·관련 문서 선정은 GoalAgent

B) 여신 상세 해설은 LLM 없이 Metrics 비교 구조만(숫자+고정 요약 규칙). AttentionAgent는 Attention만. GoalAgent는 목표 검토·신규·관련 문서. 자연어 추가는 화면 맥락의 Agent(Dashboard면 Attention, 목표면 Goal)

C) 세 번째 Chat 컴포넌트가 추가 질문을 받고, AttentionAgent 또는 GoalAgent에 위임한다. 여신 해설은 AttentionAgent

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안으로 해줘

기록된 선택: **A**. 여신 Attention·여신 상세 해설·Dashboard 추가 질문은 AttentionAgent. 목표 검토·신규·목표 화면 추가 질문·관련 문서 선정은 GoalAgent. FR-5.4(Agent 해설)를 지키며, 여신 해설의 근거는 Metrics ID다 (D7).

---

## Question F3

FR-4.4 여신 Attention은 실적·목표·**정책 요약**을 읽습니다. D7은 Knowledge를 목표 검토·신규에만 쓰라고 했습니다. AttentionAgent의 정책 요약은 어디서 읽나요?

A) AttentionAgent는 Metrics와 현재 경영목표만 읽는다. 정책 요약은 Metrics/시드 필드다. Knowledge는 D7대로 목표 쪽만

B) AttentionAgent도 Knowledge에서 관련 정책 요약을 읽는다. D7의 “Metrics만”은 여신 상세 화면의 해설에만 적용한다

C) Attention·목표 모두 Knowledge를 읽는다. D7 B는 철회하고, 여신 상세 해설만 지표 숫자는 Metrics, 문장 생성은 AttentionAgent가 Metrics evidenceIds만 붙인다

X) Other (please describe after [Answer]: tag below)

[Answer]: 추천안으로 해줘

기록된 선택: **B**. AttentionAgent는 Knowledge에서 관련 정책 요약을 읽는다. D7의 “Metrics만”은 여신 상세 해설에만 적용한다. 목표 검토·신규는 그대로 Knowledge를 쓴다.
