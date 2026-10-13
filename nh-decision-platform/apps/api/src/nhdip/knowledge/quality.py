"""질문하기 품질 지표 (설계 §21.16 · 요구사항 ASK-08) — 감사 기록(`assist.ask` · `assist.feedback`)에서 집계한다.

별도 저장소 · 집계 작업이 없다: 질문 · 피드백이 이미 감사 기록에 남으므로(질문은 개인정보 형식 값을 가려 남김) 읽을 때 집계한다.
관리자가 보고 싶은 것은 세 가지다.
- 답을 못 하는 비율: 출처가 하나도 없는 질문(`sources=0`) — 색인에 자료가 없거나 팀 범위 밖이다.
- 사용자 평가: 피드백 '도움이 됨' 비율, 그리고 '도움이 안 됨'을 많이 받은 질문.
- 동작 방식: LLM 을 못 써서 정리만 한 답(`fallback`), 숫자 검증을 통과하지 못한 답, 의미 검색이 켜진 비율.
질문 글은 읽을 때도 한 번 더 가린다(가림 설정을 켜기 전에 쌓인 기록 대비).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from nhdip.privacy import mask_text

ASK_SQL = text(
    "SELECT count(*) AS total, count(DISTINCT actor) AS users, "
    " count(*) FILTER (WHERE detail->>'sources' = '0') AS no_source, "
    " count(*) FILTER (WHERE detail->>'mode' = 'fallback') AS fallback, "
    " count(*) FILTER (WHERE detail->>'verified' = 'false') AS unverified, "
    " count(*) FILTER (WHERE detail->>'semantic' = 'true') AS semantic, "
    " count(*) FILTER (WHERE detail->>'rewritten' = 'true') AS rewritten "
    "FROM audit.audit_log WHERE action = 'assist.ask' AND at >= now() - make_interval(days => :d)"
)
FEEDBACK_SQL = text(
    "SELECT count(*) AS total, "
    " count(*) FILTER (WHERE detail->>'helpful' = 'true') AS helpful, "
    " count(*) FILTER (WHERE detail->>'helpful' = 'false') AS unhelpful "
    "FROM audit.audit_log WHERE action = 'assist.feedback' AND at >= now() - make_interval(days => :d)"
)
# {cond} 는 이 모듈 안의 고정 조건식만 들어간다(사용자 입력 아님)
TOP_SQL = (
    "SELECT detail->>'question' AS q, count(*) AS n, max(at) AS last_at FROM audit.audit_log "
    "WHERE action = :a AND at >= now() - make_interval(days => :d) AND {cond} AND detail->>'question' IS NOT NULL "
    "GROUP BY 1 ORDER BY n DESC, max(at) DESC LIMIT :lim"
)
DAILY_SQL = text(
    "SELECT (at AT TIME ZONE 'UTC')::date AS day, count(*) AS total, count(*) FILTER (WHERE detail->>'sources' = '0') AS no_source "
    "FROM audit.audit_log WHERE action = 'assist.ask' AND at >= now() - make_interval(days => :d) GROUP BY 1 ORDER BY 1"
)


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def _top(session: Session, action: str, cond: str, days: int, lim: int) -> list[dict[str, Any]]:
    rows = session.execute(text(TOP_SQL.format(cond=cond)), {"a": action, "d": days, "lim": lim * 3}).all()  # 가림 뒤 합쳐지는 몫을 감안해 넉넉히 읽는다
    merged: dict[str, dict[str, Any]] = {}
    for q, n, last in rows:
        key = mask_text(str(q))[:200]  # 가린 뒤 같아지는 질문은 합친다
        cur = merged.setdefault(key, {"question": key, "count": 0, "lastAt": last.isoformat() if last else None})
        cur["count"] += int(n)
    return sorted(merged.values(), key=lambda x: -x["count"])[:lim]


def quality(session: Session, days: int = 7, top: int = 10) -> dict[str, Any]:
    days = max(1, min(int(days), 90))
    a = session.execute(ASK_SQL, {"d": days}).one()
    f = session.execute(FEEDBACK_SQL, {"d": days}).one()
    total, rated = int(a.total), int(f.helpful) + int(f.unhelpful)
    return {
        "days": days,
        "ask": {
            "total": total, "users": int(a.users), "noSource": int(a.no_source), "noSourceRate": _rate(int(a.no_source), total), "fallback": int(a.fallback), "fallbackRate": _rate(int(a.fallback), total),
            "unverified": int(a.unverified), "unverifiedRate": _rate(int(a.unverified), total), "semanticRate": _rate(int(a.semantic), total), "rewrittenRate": _rate(int(a.rewritten), total),
        },
        "feedback": {"total": int(f.total), "helpful": int(f.helpful), "unhelpful": int(f.unhelpful), "helpfulRate": _rate(int(f.helpful), rated), "responseRate": _rate(int(f.total), total)},
        "unanswered": _top(session, "assist.ask", "detail->>'sources' = '0'", days, top),
        "unhelpful": _top(session, "assist.feedback", "detail->>'helpful' = 'false'", days, top),
        "daily": [{"day": d.isoformat(), "total": int(t), "noSource": int(n)} for d, t, n in session.execute(DAILY_SQL, {"d": days}).all()],
    }
