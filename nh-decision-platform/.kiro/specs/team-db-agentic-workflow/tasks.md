# 작업 — Phase P (요구사항 · 설계: 같은 폴더)

- [x] P.1 분석 에이전트 팀 DB 컨텍스트 (TDB-01~06 · 09 · GAP-01)
  - [x] P.1.1 `analysis_agents/team.py` — team_of · dataset_scopes · periods · related_kpis · graph_context · build_context
  - [x] P.1.2 `team_context` 노드 · `_nodes` 사슬(근거 검색 항상 · concepts_from_context · team_only)
  - [x] P.1.3 `n_retrieve` — 문맥 개념 · 팀 문서 우선
  - [x] P.1.4 `render` — 참고한 팀 데이터 절 · bank_data 근거 · `dynamic_task` 입력
- [x] P.2 조건 · 전파 (TDB-07 · AGW-02~04 · GAP-03 · GAP-05 · GAP-06)
  - [x] P.2.1 approve — team · common 조건, 기본 cron(AGW-06)
  - [x] P.2.2 dispatcher — team · common · common_doc · metrics.changed 매칭, 변경 없음 건너뛰기, 영향 판단 기록
  - [x] P.2.3 engine — metrics.changed 이벤트 · documents owner_org 페이로드 · ingest unchanged
  - [x] P.2.4 seed — impact_assessor 에이전트 · 기존 분석 에이전트 노드/조건 보강 · 설정 기본값
- [x] P.3 상태 표시 (AGW-08 · AGW-09)
  - [x] P.3.1 `GET /analysis/status` · `GET /admin/automation`
  - [x] P.3.2 웹 RefreshStatus · /admin/automation 페이지 · 화면 등록
- [x] P.4 업로드 기준일 · 메모 (UPV-01~09 · GAP-04 · GAP-07 · GAP-08)
  - [x] P.4.1 이전 0021 · 모델 memo · requested_by · ingest 저장 · 승인 경로
  - [x] P.4.2 placement · 요청 검사(불일치 차단 · 중복 경고) · periods API
  - [x] P.4.3 current_rows 정규화 · 기준일 열 없는 자료
  - [x] P.4.4 웹 — 자료 올리기 안내 · 보관 기준일 · 반영 미리보기 · 검토 카드
  - [x] P.4.5 빌더 — 보관 기간 · 비교 토큰 안내(UPV-09) · 카탈로그 범위 표시(TDB-08)
- [x] P.5 관리자 메뉴 (ADM2-01~04)
- [x] P.6 빈틈 (GAP-02 검증 0/0)
- [x] P.7 시험 · 빌드 · 화면 확인 · 문서 · 커밋 · 푸시

## 검증 (2026-10-16)
- pytest 전체 418 통과 · 12 건너뜀(메뉴 묶음 이름 시험 2건은 새 묶음으로 고침) · 새 시험 tests/test_phase_p.py 4건
- web tsc · eslint · vitest 193 · next build 통과, 화면 캡처(분석 에이전트 보고서 팀 데이터 절 · 갱신 상태 · /admin/automation · 자료 올리기 보관 기준일)
