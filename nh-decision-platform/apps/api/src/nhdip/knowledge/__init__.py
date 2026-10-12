"""질문하기 통합 지식 색인 · 팀별 컬렉션 · 하이브리드 검색 (요구사항 §21 · 설계 §21).

핵심 계층이다 — HTTP(FastAPI) 계층을 가져오지 않는다. 사용자 조직 · 화면 리소스 같은 HTTP 계층 정보는
호출하는 쪽(api/assist.py)이 `collections.AccessContext` 로 만들어 넘긴다.

  collections  컬렉션 정의 · 접근 범위 해석 · 산출물 → 컬렉션 배정 · SQL 사전 필터
  render       산출물 JSON → 읽을 수 있는 글 블록 → 검색 단위(청크)
  indexer      청크 upsert(세대 동기화 · 멱등) · 개념 태깅 · 지점 범위
  maintenance  워커 주기 작업 — 대조 · 임베딩 채우기 · 그래프 이벤트
  query        질의 이해 — 질의어 · 개념 · 개념 확장 · 후속 질문 재작성
  search       하이브리드 검색 — 키워드 · 의미 · 그래프 채널 → 가중 RRF → 재순위
"""
