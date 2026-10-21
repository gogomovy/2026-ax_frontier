"""분석 레지스트리 (Phase C · DAG-07 · Q101) — 부서 분석 공간(설정 `analysis.spaces`) + 활성 분석 에이전트.

공간 = 부서 분석 화면 하나: 이름 · 화면 경로 · 기존 탭 목록 산출물 · 보고서 열람 리소스 · 보고서 키 접두어 · 범위(영업점 지점).
분석 목록 = 공간의 기존 탭(산출물 그대로) + 그 공간의 분석 에이전트 탭(`an-<slug>`, 보고서 `report.an-<slug>` 가 게시된 것).
기존 분석의 계산 노드 · 탭 산출물은 건드리지 않는다(Q102) — 표시 단계만 같은 목록 · 같은 보고서 화면을 쓴다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import AnalysisAgent, Setting
from nhdip.views.store import get_current, get_current_row

# 공간의 구조(화면 경로 · 산출물 키 · 열람 리소스)는 제품 화면과 맞물린 기본값이다. 이름(label)은 구성이 없을 때의 표시용 기본값일 뿐 —
# 실제 표시 이름은 spaces() 가 화면 · 업무 영역 · 조직에서 정한다(config_label). 새 부서 공간은 설정 analysis.spaces 로 더한다(DAG-07)
DEFAULT_SPACES: dict[str, dict[str, Any]] = {
    "risk": {"label": "사업부서", "path": "/risk/analysis", "tabs": "analysis_tabs", "tabsResource": "analysis_tabs", "resource": "reports", "reportPrefix": "report.", "builder": True, "domain": "RISK", "persona": "P2"},
    "branch": {"label": "영업점", "path": "/branch/analysis", "tabs": "branch_tabs", "tabsResource": "branch_tabs", "resource": "branch_reports", "reportPrefix": "report.branch-", "scoped": "office", "builder": False, "domain": "BRANCH", "persona": "P3"},
    # 종합기획부(고정) — 기존 [데이터 분석] 화면의 탭으로 (Q109). 기존 탭(여신 실적)은 화면 안 탭이라 산출물 탭 목록은 없음
    "hq": {"label": "종합기획부", "path": "/hq/analysis", "tabs": None, "tabsResource": "hq_reports", "resource": "hq_reports", "reportPrefix": "report.", "builder": True, "domain": "HQ", "persona": "P1"},
}
SEV_ORDER = {"info": 0, "watch": 1, "caution": 2, "critical": 3}
LIVE = ("active", "paused")


def config_label(session: Session, path: str | None) -> str | None:
    """분석 공간 이름을 운영 구성에서 — 그 화면(경로)의 메뉴 묶음 → [화면 설정 › 업무 영역] 단위의 조직 이름(없으면 묶음 이름).
    부서 이름을 코드에 두지 않는다: 조직 · 화면 · 업무 영역을 바꾸면 분석 결과 제목 · 공유 표시도 따라 바뀐다."""
    from nhdip.models import OrgUnit, Screen
    from nhdip.ui_config import value_of

    if not path:
        return None
    scr = session.execute(select(Screen).where(Screen.path == path, Screen.active).order_by(Screen.sort)).scalars().first()
    if scr is None or not scr.section:
        return None
    for spec in (value_of(session, "ui.scopes") or {}).values():
        units = spec.get("units") if isinstance(spec, dict) else None
        for u in units or []:
            if isinstance(u, dict) and u.get("section") == scr.section and u.get("org"):
                org = session.get(OrgUnit, u["org"])
                if org is not None:
                    return org.name
    return scr.section


def spaces(session: Session) -> dict[str, dict[str, Any]]:
    """분석 공간 — 기본 정의(DEFAULT_SPACES: 화면 경로 · 산출물 키 · 리소스) + 설정 analysis.spaces.
    이름(label)은 설정에 적었으면 그것, 아니면 운영 구성(화면 · 업무 영역 · 조직)에서 — 기본 정의의 이름은 구성이 없을 때만 쓴다."""
    s = session.get(Setting, "analysis.spaces")
    v = s.value if s is not None and isinstance(s.value, dict) else {}
    out = {}
    for k, d in {**DEFAULT_SPACES, **v}.items():
        if isinstance(d, dict) and d.get("enabled", True) is not False:
            sp = {**DEFAULT_SPACES.get(k, {}), **d, "key": k}
            if not (isinstance(v.get(k), dict) and v[k].get("label")):
                sp["label"] = config_label(session, sp.get("path")) or sp.get("label") or k
            out[k] = sp
    return out


def space(session: Session, key: str) -> dict[str, Any] | None:
    return spaces(session).get(key)


def agent_for_tab(session: Session, tab_key: str) -> AnalysisAgent | None:
    if not tab_key.startswith("an-"):
        return None
    return session.execute(select(AnalysisAgent).where(AnalysisAgent.tab_key == tab_key)).scalar()


def report_severity(payload: dict[str, Any]) -> str:
    best = "info"
    for o in payload.get("opinions") or []:
        sv = o.get("severity") or "info"
        if SEV_ORDER.get(sv, 0) > SEV_ORDER.get(best, 0):
            best = sv
    return best


def dynamic_tabs(session: Session, space_key: str) -> list[dict[str, Any]]:
    """그 공간의 분석 에이전트 탭 — 보고서가 게시된(첫 실행이 끝난) 활성 · 일시 중지 에이전트."""
    out = []
    agents = session.execute(select(AnalysisAgent).where(AnalysisAgent.space == space_key, AnalysisAgent.status.in_(LIVE)).order_by(AnalysisAgent.approved_at, AnalysisAgent.code)).scalars().all()
    for a in agents:
        row = get_current_row(session, f"report.{a.tab_key}")
        if row is None:
            continue
        p = row.payload or {}
        out.append({
            "tabKey": a.tab_key,
            "label": a.title,
            "reportKind": "dynamic",
            "insightId": ((p.get("opinions") or [{}])[0] or {}).get("id", ""),
            "severity": report_severity(p),
            "generation": "current",
            "asOf": p.get("asOf") or "",
            "generatedAt": p.get("generatedAt") or "",
            "reportKey": f"report.{a.tab_key}",
            "dynamic": True,
            "agent": a.code,
            "status": a.status,
        })
    return out


def space_tabs(session: Session, sp: dict[str, Any], builtin: dict[str, Any] | None = None) -> dict[str, Any]:
    """기존 탭(산출물 · 범위 공간은 호출자가 지점 산출물을 넘김) + 분석 에이전트 탭."""
    base = builtin if builtin is not None else (get_current(session, sp["tabs"]) if sp.get("tabs") else None) or {}
    if builtin is None and base:
        # 보고서가 아직 자료로 계산되지 않은 기존 탭은 빼고 보인다 (M.19 · Q204 — 빈 DB 에 시연 탭이 남지 않게)
        from nhdip.views.readiness import session_lookup, tabs_gate

        base = tabs_gate(base, session_lookup(session), lambda t: report_key(sp, t))
    current = list(base.get("current") or [])
    have = {t.get("tabKey") for t in current}
    current += [t for t in dynamic_tabs(session, sp["key"]) if t["tabKey"] not in have]
    return {**base, "current": current, "previous": list(base.get("previous") or [])}


def report_key(sp: dict[str, Any], tab_key: str) -> str:
    return f"report.{tab_key}" if tab_key.startswith("an-") else f"{sp.get('reportPrefix') or 'report.'}{tab_key}"


def space_for_report(session: Session, tab_key: str) -> dict[str, Any] | None:
    """분석 에이전트 보고서(`an-*`)의 공간 — 열람 리소스 검사용. 기존 보고서는 None."""
    a = agent_for_tab(session, tab_key)
    return space(session, a.space) if a is not None else None
