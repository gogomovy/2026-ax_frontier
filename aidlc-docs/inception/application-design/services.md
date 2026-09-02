# Services

응용 서비스는 `apps/api` HTTP 뒤에서 도메인 모듈을 오케스트레이션한다. Web은 이 HTTP만 호출한다.

---

## SessionService
- **책임**: 로그인, Persona, 진입 경로
- **사용**: Identity
- **스토리**: US-LOGIN-01, US-LOGIN-02

## DashboardQueryService
- **책임**: 메인 한 번에 카드 + Attention 목록 + 보고 목록
- **오케스트레이션**: Metrics.listSectorCards, Attention.listDashboard (여신 항목이 없으면 AttentionAgent.selectLoanAttentions 후 Attention.saveLoanItems), ReportRequest.list
- **규칙**: 비여신 Attention은 Mock만. 여신 AgentResult에 evidenceIds 없으면 목록에 올리지 않음
- **스토리**: US-A-01, US-A-02

## LoanDetailQueryService
- **책임**: 여신 상세 구성
- **오케스트레이션**: Attention.getBySector(여신), Metrics 세 영역, AttentionAgent.commentLoan(영역별). 해설은 Metrics evidenceIds만
- **스토리**: US-A-03, US-A-04

## GoalReviewCommandService
- **책임**: Attention/보고 → 검토 필요사항
- **사용**: ManagementGoal.addReviewItem
- **스토리**: US-A-05

## GoalWorkspaceQueryService
- **책임**: 여신 설정 화면 읽기
- **오케스트레이션**: ManagementGoal.listCurrent, listReviewNeeds, GoalAgent.reviewGoals, GoalAgent.proposeNew (selectRelatedDocuments로 Knowledge 패킷)
- **스토리**: US-B-01, US-B-02, US-B-04(보기)

## GoalCommandService
- **책임**: 확인·신규 추가. History, 생성방식, 상태, 현재 목표 저장
- **사용**: ManagementGoal keep / apply* / add*
- **쓰지 않음**: Goal Query 전파 모델은 별도 서비스
- **스토리**: US-B-03, US-B-04(추가)

## GoalPropagationQueryService
- **책임**: 이후 사업부서가 읽을 현재 목표. UI 없음
- **사용**: ManagementGoal.getCurrentForPropagation
- **스토리**: US-D-01

## KnowledgeCommandService
- **책임**: 업로드·기사 확정. 업로드 시 Extraction.extract 후 경로·텍스트 저장
- **사용**: Knowledge, Extraction
- **스토리**: US-AUX-04, US-AUX-05

## KnowledgeQueryService
- **책임**: 원문, 관련 문서, 공식 검색, 기사 후보
- **사용**: Knowledge.searchOfficial, getEvidence, listRelated
- **호출자**: GoalsUi(원문), GoalAgent, AttentionAgent(정책 요약)
- **스토리**: US-C-01, US-AUX-05, F3 B

## FollowUpService
- **책임**: 자연어 추가 질문. Dashboard/여신이면 AttentionAgent, 목표면 GoalAgent
- **스토리**: US-AUX-03

## ReportRequestCommandService
- **책임**: 생성 API만. UI 없음
- **사용**: ReportRequest.create
- **스토리**: US-D-02

## AdminSeedService
- **책임**: 시드 쓰기
- **사용**: AdminSeed → Metrics, ManagementGoal
- **스토리**: US-AUX-02

---

## 오케스트레이션 메모

- LLM은 요청-응답. 큐/폴링 없음
- GoalAgent는 제안을 만들 뿐 현재 목표를 쓰지 않는다. 쓰기는 GoalCommandService
- AttentionAgent는 여신 Attention을 만들고 Attention 모듈이 저장한다
- OpenAI 실패 시 숨기지 않음 (NFR-6.4). 표시 방식은 NFR Design
