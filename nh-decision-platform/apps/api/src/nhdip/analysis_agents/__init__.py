"""분석 에이전트 (Phase C · DAG-01~09 · Q100 · Q103).

사용자 글(도메인 지식 · 하고 싶은 분석) → ① 정제 에이전트(`refine`) → 분석 명세(AnalysisSpec, `spec.validate_spec` 로 허용 목록 검증)
→ 미리보기(`lifecycle.preview` — 같은 노드를 한 트랜잭션에서 돌리고 되돌림) → 관리자 승인(`lifecycle.approve`)
→ 지표(`dyn_*`) · 워크플로(`wf_an_*`) · 그 분석 전용 에이전트(`an_*`) · 트리거 생성
→ 실행: 커널 계산 → ② 동적 수행(`dynamic_task`, 전용 에이전트가 판단 · 서술) → ③ 범용 렌더링(`render_report`, 결정론) → 검증(critic) → 게시.
"""
