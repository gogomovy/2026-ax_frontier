"""자료 전 화면 거르기 (Phase M 후속 M.19 · DEL-14 · Q204).

시드는 값 없는 화면 틀(0세대)을 게시한다 — 워크플로가 같은 틀에 계산 수치를 채워 서술을 게시하므로 틀 자체는 지우지 않는다(Phase I · Q138).
대신 **읽을 때** 아직 계산되지 않은 시연 서술을 업무 화면 · 건수 · AI 어시스턴트 색인에서 뺀다. 자료를 올려 워크플로가 돌면 같은 항목이 그대로 나타난다.

- 서술(statement + figures): 기준일(asOf)이 찍혔거나 수치가 하나라도 계산된 것만. 목록에서는 빼고, 단독 값이면 None.
- 기준일 키가 있는 화면 산출물: `computed` 를 붙인다. 계산 전이면 근거(evidence) 목록 · 해설(narrative)을 비운다.
- 보고서(report.*): 계산 전이면 없음(None → 404) — 분석 탭 목록에서도 뺀다(이전 분석 탭은 현재 탭이 하나라도 있을 때만).
- 경영목표 제안: 추천값이 계산된 것만. 수행방안: 근거 인사이트나 연결 보고서가 계산된 것만. 영업점 전파 목표: 수치가 있는 것만.
  전파 경로(cascade): 경영목표 · 전파 목표 중 하나라도 계산됐을 때만.
시연 자료가 올라간 DB 에서는 아무것도 빼지 않는다(시험 test_reset_data).
"""
from __future__ import annotations

from typing import Any, Callable

from .template import is_figure

Lookup = Callable[[str], Any]
INSIGHT_KEYS = ("insights", "attentions", "risk_dashboard", "hq_dashboard")


def has_value(obj: Any) -> bool:
    """수치(Figure) 중 값이 계산된 것이 하나라도 있는지."""
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if is_figure(o) and o.get("value") is not None and not isinstance(o.get("value"), bool):
                return True
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return False


def is_statement(d: Any) -> bool:
    return isinstance(d, dict) and "statement" in d and "figures" in d


def statement_ready(d: dict[str, Any]) -> bool:
    return bool(d.get("asOf")) or has_value(d.get("figures"))


def has_figure(obj: Any) -> bool:
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if is_figure(o):
                return True
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return False


def computed(payload: Any) -> bool:
    """산출물이 자료로 계산됐는지 — 기준일이 찍혔거나 수치가 하나라도 있다. 수치 자리가 아예 없으면(글만 있는 산출물) 판단할 근거가 없어 계산된 것으로 본다."""
    if isinstance(payload, dict) and payload.get("asOf"):
        return True
    return has_value(payload) or not has_figure(payload)


def reviewable(p: dict[str, Any]) -> bool:
    """검토할 수 있는 경영목표 제안 — 추천값이 계산된 것(방향만 제시하는 제안 포함)."""
    rec = p.get("recommendation") or {}
    return rec.get("mode") == "direction_only" or any(rec.get(k) is not None for k in ("low", "high", "value"))


def prune(o: Any) -> Any:
    """계산되지 않은 서술을 뺀 사본 — 목록에서는 항목을 빼고, 단독 값이면 None."""
    if isinstance(o, list):
        return [prune(x) for x in o if not (is_statement(x) and not statement_ready(x))]
    if isinstance(o, dict):
        return {k: (None if is_statement(v) and not statement_ready(v) else prune(v)) for k, v in o.items()}
    return o


def _blank_uncomputed(o: Any) -> None:
    """계산 전 산출물 — 해설(narrative)은 비우고, 목록 항목에 박힌 시연 상태(수치를 가진 항목의 severity)는 None 으로."""
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if isinstance(x.get("narrative"), str):
                x["narrative"] = ""
            stack.extend(x.values())
        elif isinstance(x, list):
            for it in x:
                if isinstance(it, dict) and isinstance(it.get("severity"), str) and any(is_figure(v) for v in it.values()):
                    it["severity"] = None
            stack.extend(x)


def _blank_rows(o: Any) -> None:
    """수치가 하나도 계산되지 않은 행(수치를 가진 dict) — 시연 판정 문구 · 한도 판정 · 출처 문서를 비운다(값이 생기면 워크플로가 채운다)."""
    stack = [o]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if not is_figure(x) and "statement" not in x:
                figs = [v for v in x.values() if is_figure(v)]
                if figs and not any(f.get("value") is not None for f in figs):
                    if isinstance(x.get("verdict"), str) and x["verdict"] not in ("", "–"):
                        x["verdict"] = ""
                    if isinstance(x.get("passed"), bool):
                        x["passed"] = None
                    if isinstance(x.get("doc"), dict):
                        x["doc"] = None
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)


def report_ready(lookup: Lookup, key: str) -> bool:
    p = lookup(key)
    return isinstance(p, dict) and computed(p)


def plan_ready(p: dict[str, Any], lookup: Lookup) -> bool:
    from .store import find_insight

    tab, sid = p.get("linkedTabKey"), p.get("sourceInsightId")
    if not tab and not sid:
        return True  # 연결이 없는 수행방안은 판단할 근거가 없어 그대로 둔다
    if tab and report_ready(lookup, f"report.{tab}"):
        return True
    if sid:
        arts = {k: v for k in INSIGHT_KEYS if (v := lookup(k)) is not None}
        ins = find_insight(arts, sid)
        if ins is not None and statement_ready(ins):
            return True
    return False


def tabs_gate(payload: dict[str, Any], lookup: Lookup, report_key: Callable[[str], str] | None = None) -> dict[str, Any]:
    """분석 탭 — 보고서가 계산된 탭만(분석 에이전트 탭은 보고서가 게시된 뒤에만 생기므로 그대로)."""
    rk = report_key or (lambda t: f"report.{t}")
    cur = [t for t in payload.get("current") or [] if t.get("dynamic") or report_ready(lookup, t.get("reportKey") or rk(str(t.get("tabKey") or "")))]
    return {**payload, "current": cur, "previous": list(payload.get("previous") or []) if cur else []}


def gate(key: str, payload: Any, lookup: Lookup | None = None, *, flag: bool = True) -> Any:
    """화면에 보낼 산출물 — 계산 전 시연 서술을 뺀 사본(보고서가 계산 전이면 None). lookup 은 다른 산출물 현재 세대(없으면 교차 판단 생략).
    flag=False 면 `computed` 표시를 붙이지 않는다(색인 — 같은 내용이면 같은 청크 해시)."""
    if payload is None:
        return None
    bkey = key.partition("@")[0]
    if bkey.startswith("report."):
        return prune(payload) if computed(payload) else None
    if bkey == "proposals" and isinstance(payload, list):
        return [p for p in payload if not isinstance(p, dict) or reviewable(p)]
    if bkey == "branch_targets" and isinstance(payload, list):
        return [t for t in payload if not isinstance(t, dict) or has_value(t)]
    if lookup is not None:
        if bkey == "analysis_tabs" and isinstance(payload, dict):
            return tabs_gate(payload, lookup)
        if bkey == "action_plans" and isinstance(payload, list):
            return [p for p in payload if not isinstance(p, dict) or plan_ready(p, lookup)]
        if bkey == "cascade" and isinstance(payload, list):
            return payload if has_value(lookup("goals")) or has_value(lookup("branch_targets")) else []
    out = prune(payload)
    _blank_rows(out)
    if isinstance(out, dict) and "asOf" in out:
        ok = computed(payload)
        if flag:
            out["computed"] = ok
        if not ok:
            if isinstance(out.get("evidence"), list):
                out["evidence"] = []
            _blank_uncomputed(out)
    return out


def session_lookup(session: Any) -> Lookup:
    """요청 하나 안에서 같은 산출물을 다시 읽지 않는 조회 함수."""
    from .store import get_current

    cache: dict[str, Any] = {}

    def look(k: str) -> Any:
        if k not in cache:
            cache[k] = get_current(session, k)
        return cache[k]

    return look
