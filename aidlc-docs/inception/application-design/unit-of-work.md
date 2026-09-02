# Unit of Work

계획: `aidlc-docs/inception/plans/unit-of-work-plan.md`  
배포: 로컬 `apps/web` 프로세스 + `apps/api` 프로세스 + PostgreSQL. 단위는 Construction 반복 묶음이지 별도 스케일 단위가 아니다.

---

## 코드 배치 (greenfield, FR-10)

방법론의 루트 `src/{unit-name}/`는 쓰지 않는다.

```
apps/web/src/          # 화면 모듈 (단위가 기능을 추가)
apps/web/tests/
apps/api/src/identity
apps/api/src/metrics
apps/api/src/attention
apps/api/src/report-request
apps/api/src/management-goal
apps/api/src/knowledge
apps/api/src/extraction
apps/api/src/attention-agent
apps/api/src/goal-agent
apps/api/src/admin-seed
apps/api/tests/
```

프레임워크 패키지 매니저 파일은 Construction NFR에서 정한다.

---

## U-KNOWLEDGE

- **종류**: Module (코드는 `apps/web` KnowledgeUi + `apps/api` Knowledge·Extraction)
- **책임**: 정책·의사결정 문서 등록, HWP/PDF 추출, 공식 도메인 검색, 기사 확정, 근거 원문, Agent가 읽을 관련 문서·정책 요약 시드
- **Web**: KnowledgeUi
- **API**: Knowledge, Extraction
- **선행**: 없음
- **스토리**: US-C-01, US-AUX-04, US-AUX-05

## U-MONITOR

- **종류**: Module
- **책임**: Mock 로그인, 한/영, Dashboard, 여신 상세, 여신 Attention·해설, 보고 **목록**, 검토 대상 **등록**
- **Web**: WebShell, DashboardUi, LoanDetailUi
- **API**: Identity, Metrics, Attention, AttentionAgent, ReportRequest.list, ManagementGoal.addReviewItem
- **선행**: U-KNOWLEDGE (정책 요약 읽기, 시드)
- **스토리**: US-LOGIN-01, US-LOGIN-02, US-A-01~04, US-A-05(등록), US-AUX-01, US-AUX-03(Dashboard·여신)

## U-SET-DIRECTION

- **종류**: Module
- **책임**: 여신 경영목표 화면, Agent 검토·신규, 확인·추가, 검토 필요사항 **표시**, 목표 화면 추가 질문, 근거 원문 열기(Knowledge 조회 사용)
- **Web**: GoalsUi
- **API**: ManagementGoal Command/목록/History, GoalAgent
- **선행**: U-KNOWLEDGE, U-MONITOR (Metrics·검토 등록·현재 목표 시드)
- **스토리**: US-B-01~04, US-A-05(목록), US-C-01(목표 화면에서 원문), US-AUX-03(목표 화면)

## U-PROPAGATE

- **종류**: Module
- **책임**: 확정 목표 전파 읽기 API(UI 없음), 확인·보고 **생성** API, 시드 관리 화면
- **Web**: AdminUi
- **API**: GoalPropagationQuery, ReportRequest.create, AdminSeed
- **선행**: U-SET-DIRECTION (현재 목표), U-MONITOR (보고 목록과 같은 저장소)
- **스토리**: US-D-01, US-D-02, US-AUX-02

---

## Construction 순서

1. U-KNOWLEDGE  
2. U-MONITOR  
3. U-SET-DIRECTION  
4. U-PROPAGATE  

한 작업 흐름이 이 순서로 Functional Design부터 반복한다.
