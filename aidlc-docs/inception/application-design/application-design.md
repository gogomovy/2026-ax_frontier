# Application Design

종합기획부 Persona Prototype. 계획 `aidlc-docs/inception/plans/application-design-plan.md`의 생성 규칙을 따른다.

상세 표: `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`. 업무 규칙 세부는 Construction Functional Design.

---

## 1. 구조

- `apps/web`: 화면 모듈. Journey UI + Shell + Admin
- `apps/web`는 HTTP로 `apps/api`만 호출한다
- `apps/api`: 도메인 모듈형 모듈러 모노리스. 모듈 간 공개 인터페이스만
- PostgreSQL, 로컬 파일, OpenAI, 공식 도메인 HTTP는 API만 접근
- 프레임워크 이름은 이 문서에 두지 않는다 (NFR-1.2)

---

## 2. 컴포넌트 목록

### Web
WebShell, DashboardUi, LoanDetailUi, GoalsUi, KnowledgeUi, AdminUi

### API
Identity, Metrics, Attention, ReportRequest, ManagementGoal, Knowledge, Extraction, AttentionAgent, GoalAgent, AdminSeed

### 공유 계약
`AgentResult.evidenceIds` 필수. 빈 목록은 실패. 당행 Data / 내부 경영방향 / 외부 정책 / 확정 기사를 구분한다.

---

## 3. Agent 경계

| 컴포넌트 | 하는 일 | 읽기 |
|---|---|---|
| AttentionAgent | 여신 Attention 선정, 여신 상세 해설, Dashboard·여신 추가 질문 | Attention: Metrics + 현재 목표 + Knowledge 정책 요약. 해설: Metrics만 |
| GoalAgent | 기존 목표 검토, 신규 제안, 목표 화면 추가 질문, 관련 문서 선정 | Metrics + Knowledge(관련 문서·확정 기사·공식 검색 결과) + 현재 목표. 전 문서 투입 금지 |

확정 목표 숫자는 어느 Agent도 만들지 않는다. 쓰기는 GoalCommandService.

---

## 4. 서비스

| 서비스 | 역할 |
|---|---|
| SessionService | 로그인·진입 |
| DashboardQueryService | 카드 + Attention + 보고. 여신 Attention 없으면 Agent 호출 후 저장 |
| LoanDetailQueryService | 상세 Attention + 지표 + 해설 |
| GoalReviewCommandService | 검토 대상 등록 |
| GoalWorkspaceQueryService | 설정 화면 읽기 + Agent 제안 |
| GoalCommandService | 확인·신규 저장·History |
| GoalPropagationQueryService | 사업부서용 현재 목표 읽기 (UI 없음) |
| KnowledgeCommandService / QueryService | 업로드(추출 포함), 원문, 검색, 기사 확정 |
| FollowUpService | 화면 맥락에 따라 AttentionAgent 또는 GoalAgent |
| ReportRequestCommandService | 생성 API |
| AdminSeedService | 시드 쓰기 |

---

## 5. 의존 요약

브라우저 → API → (PostgreSQL | 파일 | OpenAI | 공식 HTTP)

DashboardUi는 Attention + ReportRequest + Metrics를 조합한다. GoalsUi는 ManagementGoal + GoalAgent + Knowledge 원문을 조합한다.

순환 없음: Agent끼리 호출하지 않음. GoalAgent는 목표를 읽기만 함.

다이어그램: `component-dependency.md`

---

## 6. 스토리·FR 대조

| 스토리 | 화면 | 서비스/모듈 |
|---|---|---|
| US-LOGIN-01, 02 | WebShell | SessionService, Identity |
| US-A-01 | DashboardUi | DashboardQueryService, Attention, Metrics, AttentionAgent |
| US-A-02, US-D-02 | DashboardUi / API만 | ReportRequest |
| US-A-03, US-A-04 | LoanDetailUi | LoanDetailQueryService, Metrics, AttentionAgent |
| US-A-05 | Dashboard/Loan | GoalReviewCommandService |
| US-B-01~04 | GoalsUi | GoalWorkspaceQuery, GoalCommand, GoalAgent |
| US-C-01 | GoalsUi / KnowledgeUi | KnowledgeQueryService |
| US-D-01 | 없음 | GoalPropagationQueryService |
| US-AUX-01 | WebShell | setLocale |
| US-AUX-02 | AdminUi | AdminSeedService |
| US-AUX-03 | Dash/Loan/Goals | FollowUpService |
| US-AUX-04, 05 | KnowledgeUi | Knowledge + Extraction |

모순 없음으로 본 항목:

- 비여신 Attention은 Attention 모듈 Mock. AttentionAgent는 여신만
- 확인·보고 생성 UI 없음. ReportRequest.create만
- 사업부서 화면 없음. GoalPropagationQuery만
- 여신 해설은 Knowledge를 읽지 않음. Attention의 정책 요약은 Knowledge
- HWP 뷰어 없음. Extraction + 다운로드

사용자 스토리 없음: FR-2.7, FR-10 (구현 위치·식별자 관례)

---

## 7. 의도적으로 여기 두지 않는 것

- Card 크기, Chart, Button 위치
- 프론트·백엔드 프레임워크
- OpenAI 실패 UI 문구의 최종 카피 (NFR Design)
- 단위(Unit) 경계 (Units Generation)
