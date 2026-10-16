# 설계 — 팀 DB 활용 분석 에이전트 · 변경 감지 에이전틱 워크플로 · 업로드 기준일 · 관리자 메뉴 (Phase P)

요구사항: [requirements.md](./requirements.md) (TDB · AGW · UPV · ADM2 · GAP)

## 1. 분석 에이전트 — 팀 DB 컨텍스트

### 1.1 노드 사슬 (승인 · 미리보기 공통, `lifecycle._nodes`)

```
load_inputs → compute_metrics → team_context(새) → retrieve_evidence(항상 · 선택 노드) → dynamic_task → render_report → critic → publish
```

- `team_context` (`workflow/analysis_nodes.py`, 결정론 · 선택 노드) — `analysis_agents/team.py` 의 `build_context()` 결과를 `ctx.state["team_context"]`,
  개념 키를 `ctx.state["context_concepts"]`, 팀 조직을 `ctx.state["team_orgs"]` 에 둔다.
- `retrieve_evidence` 설정: `{query: 명세 evidence.query 또는 제목+목적, doc_classes, k, optional, respect_plan: false, concepts_from_context: true, team_only: true}`.
  - `concepts_from_context` — 설정 `concepts` 가 없으면 `ctx.state.context_concepts` 를 그래프 필터로.
  - `team_only` — 소유 검사 뒤 팀 조직 · 소유 없음 · 공통 분류 문서만. 남는 게 없으면 원래 후보로 되돌리고 메모.
- 기존 승인 에이전트: 1회 보강(`seed` `analysis-agents-team-v1`)이 노드를 다시 만들고 팀 · 공통 조건을 더한다(명세 · 지표는 그대로).

### 1.2 `analysis_agents/team.py`

| 함수 | 역할 |
|---|---|
| `team_of(session, org_code)` | `orgs.steward_scope` → `{code, name, orgs:set}` (하위 조직 포함) |
| `team_of_agent(session, agent_code \| actor)` | 요청자(`AnalysisAgent.requested_by`) 소속 기준 |
| `dataset_scopes(session, team_orgs)` | 데이터셋별 `scope` = team(팀 소유 현재 판) · common(공통 통합 DB) · bank(소유 없음) · other(다른 부서), `owners` |
| `periods(session, ds)` | 현재 판 → `[{asOf, version, rows, memo, committedAt, owner}]` 기준일 순 |
| `build_context(session, spec, team, *, inputs, max_datasets, max_kpis)` | 정형(입력 + 팀 + 공통 + 그래프 연관 → 관련도 순) · KPI · 그래프 관계 · 개념 키 |
| `graph_context(codes)` | Neo4j: 입력 자료의 이웃(개념 · 지표 · 흐름 · DocClass) + 같은 개념/지표를 공유하는 다른 자료. `graph_up()` 차단기 공유 |

관련도 = `refine._score`(이름 · 설명 · 열 낱말) + 범위 가산(team +4 · common +2 · graph 연관 +3). 입력 자료는 항상 포함.

### 1.3 결과 (`render.py`)

- `team_section(ctx_team, evidence)` → 보고서 마지막 절 `sec-team` "참고한 팀 데이터 (정형 · 근거 · 온톨로지)":
  - 표 ① 정형 DB(PostgreSQL): 자료 · 구분(우리 팀/공통/전행/다른 부서) · 쓰임(계산 입력/참고) · 보관 기준일(첫~끝 · n개) · 현재 판 · 행
  - 표 ② 상위 부서 KPI: 지표 · 흐름 · 최근 값 · 직전 값(단위 표기는 서식)
  - 표 ③ 근거 문서(Elasticsearch): 문서 · 분류 · 쪽 · 검색 엔진
  - 표 ④ 온톨로지(Neo4j): 대상 · 관계 · 연결 대상
  - 안내 문단: 팀 이름 · 그래프 · 검색 엔진 사용 여부
- 의견 근거: 문서 근거 앞에 `bank_data` 근거(`sourceKind: calc_run`, 입력 자료 이름 · 판 · 기준일, `figureId`) → critic `evidence_present` 가 실제 상태를 반영.
- `dynamic_task` LLM 입력에 `teamData` 요약(자료 이름 · 기간 · 쓰임, KPI 이름 · 마커 없는 값 제외, 관계) — 수치 마커 규칙은 그대로.

### 1.4 조건 (`approve`)

기존(입력 데이터셋 · 상위 흐름 조건 사본 · cron)에 더해 `WorkflowTrigger(kind="team", target=팀 코드)` · `WorkflowTrigger(kind="common", target="*")`.
cron 이 비었고 옵션에서 명시하지 않았으면 설정 `analysis_agents.default_cron`(기본 `40 6 * * *`).

## 2. 디스패처 · 판단 에이전트

### 2.1 `match_event` 추가 규칙

| 이벤트 | 조건 | 사유 |
|---|---|---|
| `dataset.*` · `document.*` | `team` 조건 대상의 하위 조직에 `payload.owner_org` | `trigger:team(코드)` |
| `dataset.*` (`common: true`) · `document.*`(공통 분류) | `common` 조건 | `trigger:common` |
| `document.*` (공통 분류) | 근거 검색 노드가 있는 흐름(기반 흐름 제외) | `lineage:common_doc` |
| `metrics.changed` | 바뀐 지표를 `args.metric` 으로 참조하는 다른 흐름 — 그 이벤트의 실행 종료 뒤 이미 시작한 실행이 있으면 제외 | `lineage:upstream(흐름 · 지표)` |

`document.ingested` 페이로드에 `owner_org` 를 더한다.

### 2.2 `metrics.changed` (엔진)

`run_workflow` 성공(succeeded · degraded) 뒤: `ctx.eval.outcomes` 에서 `display != previous`(첫 값 포함)인 지표 중 **다른 흐름이 참조하는 것**만 모아
`emit("metrics.changed", {workflow, run, finished_at, metrics:[…≤50], chain: run_chain + [wf]})`. 참조하는 흐름이 없으면 내지 않는다.

### 2.3 영향 판단 (`impact_assessor`, 규칙 에이전트)

`dispatch_once` 가 자동 이벤트(수동 · 정기 제외)를 처리할 때 `ops.agent_decision(agent_code="impact_assessor", decision="impact"|"skip")`:
`summary` = "자료 X 새 판 → 흐름 n개 (계보 · 팀 · 공통 · 상위)" / "변경 없음 — 같은 파일", `detail` = {event, matched(사유), blocked}.
`payload.unchanged` 이면 매칭하지 않고 `skip`. 기록 실패는 무시(디스패치 계속).

`ingest_rows`: 교체될 같은 구획 현재 판 중 해시 · 행 수가 같은 판이 있으면 `dataset.committed` 에 `unchanged: true, same_as: vN`.

## 3. 상태 조회

### 3.1 `GET /analysis/status?workflow=` (업무 화면, `_check` 와 같은 권한)

```json
{"workflow","name","state":"idle|queued|held|approval|running","pending":{"since","runAfter","causes":["자료 X 새 판",...]},
 "lastRun":{"status","finishedAt"},"triggers":{"data":n,"team":bool,"common":bool,"upstream":["흐름 이름"],"events":["경영목표 확정"],"cron":[{"expr","label","next"}]}}
```
`held` = 대기 작업의 최근 오케스트레이터 결정이 `hold`.

### 3.2 `GET /admin/automation` (관리자)

흐름별(기반 흐름 포함) 위와 같은 항목 + 최근 실행 24시간 수 · 실패 수, 최근 영향 판단 30건, 정책 요약(`workflow.debounce_default_sec` · `orchestrator.policy` 의 max_chain · route_on · require_approval · LLM 판단 켜짐).
수동 실행은 기존 `POST /admin/workflows/{code}/run`.

### 3.3 웹

- `RefreshStatus` (components/agent) — 보고서 도구 줄(`ReportView`)에서 '분석 다시 실행' 옆: "자동 갱신 · 자료 변경 시 · 매일 06:40" 칩, 대기/실행이면 "새 자료 반영 대기 중 (원인)" + 15초 폴링, 끝나면 `router.refresh()`.
- `/admin/automation` 페이지 (admin kit: `AdminPage · Card · Table · useApiData`).

## 4. 업로드 기준일 · 메모

### 4.1 이전 0021 (`0021_version_memo`)

`bank|ext.dataset_version` 에 `memo TEXT`, `requested_by VARCHAR(40)`. 승인된 요청의 `meta.note` · `requested_by` 로 채운다.

### 4.2 `data/placement.py` — `placement(session, ds, rows, *, as_of, owner_org, file_sha)`

```json
{"versionAsOf","typedAsOf","fileFrom","fileTo","fileDates":n,"action":"add|replace","replaces":{"version","asOf","memo","committedAt"}|null,
 "overlaps":[{"asOf","version"}],"duplicateOf":{"version"}|null,"noAsOfColumn":bool,"existing":[periods],"messages":[...],"error":null|"..."}
```
- 버전 기준일 = 입력값 또는 파일 기간의 마지막(`ingest_rows` 와 같은 규칙).
- `error`: 기준일 열이 있고 입력 기준일의 연-월이 파일 기간에 없음 → 요청 거절(422).
- 요청(`request_dataset` · `_proposal_request`)은 `preview.placement` 에 저장, 응답 · 검토 카드에 표시.

### 4.3 `GET /db/datasets/{code}/periods` (db_upload 리소스)

`{dataset, asOfColumn, periods:[...현재 판], history:[최근 20판 {version, asOf, status, isCurrent, memo, requestedBy, committedAt, owner}]}`.

### 4.4 `current_rows`

- 겹침 키 = (구획, `to_date(값) or str(값)`) — 형식이 달라도 같은 기간은 같은 키.
- 기준일 열이 없는 자료: 구획마다 `as_of` 가 가장 늦은 판만(같으면 최근 반영).

### 4.5 승인 (`do_approve`) → `ingest_file(..., memo=요청 메모, requested_by=요청자)`; `ingest_rows` 가 판에 저장.

## 5. 관리자 메뉴

`defs_core.SCREENS` 관리자 화면 묶음 · 정렬:

| 묶음 | 화면 |
|---|---|
| 관리자 홈 | 관리자 홈 |
| 데이터 반영 | 자료 승인 · 데이터셋·문서 · 컬럼 정의서 · 온톨로지 · AI 어시스턴트 색인 |
| 에이전트 · 자동화 | 에이전틱 파이프라인 · 자동 실행 · 변경 감지(새) · 분석 에이전트 · 워크플로 · 에이전트·프롬프트 · LLM 연동 |
| 운영 현황 | 운영 개요 · 파이프라인 · 데이터 흐름 · 운영 알림 · 비용 |
| 실행 기록 · 품질 | 에이전트 실행 · 에이전트 결정 · 수치 모니터링 · 요청 추적 · 골든셋 평가 |
| 계산 · 설정 | 지표·계산 · 판정 규칙 · 운영 설정 · 화면 설정 |
| 사용자 · 권한 | 사용자 · 조직 · 화면 권한 · 감사 로그 |

1회 보강 `admin-ia-v2`: 이전 기본 묶음(사용자와 권한 · 데이터와 지식 · AI · 에이전트 · 계산과 규칙 · 운영 모니터링 · 관리자 홈)인 화면만 옮긴다.
`AdminNav`: 현재 화면이 든 묶음만 펼침(다른 묶음은 눌러 펼침), 접힌 머리에 항목 수 · 대기 건수, 위쪽 '메뉴 찾기' 입력.

## 6. 시험

- pytest: 팀 범위 · 컨텍스트(그래프 없이) · 렌더 절 · bank_data 근거 · team/common/metrics.changed 매칭 · 변경 없음 판단 · placement(추가/교체/불일치/중복) · current_rows 형식 정규화 · 기준일 열 없는 자료 · 상태 API · 관리자 자동화 API.
- vitest: AdminNav 필터 · 접힘(순수 함수), RefreshStatus 문구.
- 빌드 · 화면 캡처: 분석 에이전트 보고서(참고한 팀 데이터 절 · 상태 칩), /admin/automation, 관리자 사이드바, 자료 올리기(보관 기준일 · 반영 미리보기).
