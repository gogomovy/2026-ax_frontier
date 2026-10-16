"""분석 에이전트 팀 데이터 (Phase P · TDB-01~06) — 명세에 적힌 자료만이 아니라 요청 팀의 3개 DB를 실행할 때마다 다시 본다.

- 정형(PostgreSQL): 명세 입력 자료 + 팀이 올린 현재 판 자료 + 공통 통합 DB 자료 + 온톨로지 연관 자료 → 관련도 순 상위 N개
- 상위 부서 KPI: 다른 흐름(종기부 목표 · 사업부서 · 영업점)이 계산한 지표의 최근 값
- 온톨로지(Neo4j): 입력 자료와 이어진 개념 · 지표 · 흐름, 같은 개념 · 지표를 공유하는 다른 자료 — 개념 키는 근거 검색 그래프 필터로
- 근거(Elasticsearch)는 근거 검색 노드가 팀 문서 우선(team_only)으로 찾는다

모두 결정론(LLM 없음)이고 읽기만 한다. 그래프 장애면 그래프 부분만 비우고 사유를 남긴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import AppUser, Dataset, Metric, MetricValue, OrgUnit, Setting, Workflow, WorkflowTrigger, source

SCOPE_LABEL = {"team": "우리 팀", "common": "공통 통합 DB", "bank": "전행", "other": "다른 부서"}
SCOPE_BONUS = {"team": 4, "common": 2, "bank": 1, "other": 0}
STRUCT_LABELS = {"Metric", "Workflow", "Artifact", "Dataset", "DatasetVersion", "Document", "BankDocument", "ExternalDocument", "DocClass", "Issuer"}
DEFAULTS = {"max_datasets": 6, "max_kpis": 6, "max_relations": 12}


@dataclass
class Team:
    code: str | None
    name: str
    orgs: set[str] = field(default_factory=set)

    def json(self) -> dict[str, Any]:
        return {"code": self.code, "name": self.name, "orgs": len(self.orgs)}


def settings(session: Session) -> dict[str, int]:
    s = session.get(Setting, "analysis_agents.team_context")
    v = s.value if s is not None and isinstance(s.value, dict) else {}
    out = dict(DEFAULTS)
    for k in DEFAULTS:
        try:
            out[k] = max(0, min(30, int(v.get(k, DEFAULTS[k]))))
        except (TypeError, ValueError):
            pass
    return out


def subtree(session: Session, root: str) -> set[str]:
    out, frontier = {root}, [root]
    while frontier:
        kids = session.execute(select(OrgUnit.code).where(OrgUnit.parent_code.in_(frontier))).scalars().all()
        frontier = [k for k in kids if k not in out]
        out.update(frontier)
    return out


def team_of(session: Session, org_code: str | None) -> Team:
    """팀 = 소속 경로에서 가장 가까운 부(DEPT) · 지역본부(REGION)와 그 아래 조직 (부서 데이터 책임자 범위와 같은 기준)."""
    from nhdip.orgs import steward_scope

    if not org_code:
        return Team(None, "전행")
    scope = steward_scope(session, org_code)
    if scope is None:
        return Team(org_code, org_code, {org_code})
    return Team(scope.code, scope.name, subtree(session, scope.code))


def team_of_user(session: Session, emp_no: str | None) -> Team:
    u = session.get(AppUser, emp_no) if emp_no else None
    return team_of(session, u.org_code if u else None)


def team_of_agent(session: Session, agent_code: str | None) -> Team:
    from nhdip.models import AnalysisAgent

    a = session.get(AnalysisAgent, agent_code) if agent_code else None
    return team_of_user(session, a.requested_by if a else None)


def dataset_scopes(session: Session, team_orgs: set[str]) -> dict[str, dict[str, Any]]:
    """{데이터셋 코드: {scope, owners}} — 현재 판의 소유 조직으로 판정. team(팀 소유 판 있음) > common > bank(소유 없음) > other."""
    out: dict[str, dict[str, Any]] = {}
    common = {d.code for d in session.execute(select(Dataset).where(Dataset.active, Dataset.common.is_(True))).scalars()}
    for origin in ("bank", "ext"):
        t = source(origin)
        for code, owner, as_of in session.execute(select(t.version.dataset_code, t.version.owner_org, t.version.as_of).where(t.version.is_current)).all():
            cur = out.setdefault(code, {"owners": set(), "scope": "other", "dates": set()})
            cur["owners"].add(owner or "")
            if as_of:
                cur["dates"].add(as_of.isoformat())
    for code, cur in out.items():
        dates = sorted(cur.pop("dates"))
        cur["periods"] = {"count": len(dates), "first": dates[0] if dates else None, "last": dates[-1] if dates else None}
        owners = cur["owners"]
        if code in common:
            cur["scope"] = "common"
        elif owners & team_orgs:
            cur["scope"] = "team"
        elif "" in owners:
            cur["scope"] = "bank"
        cur["owners"] = sorted(o for o in owners if o)
    for code in common - set(out):
        out[code] = {"owners": [], "scope": "common", "periods": {"count": 0, "first": None, "last": None}}
    return out


def periods(session: Session, ds: Dataset) -> list[dict[str, Any]]:
    """보관 중인 기준일(현재 판) — 기준일 순. 메모는 요청자 메모(없으면 비움)."""
    from nhdip.data.datasets import current_versions

    out = []
    for v in current_versions(session, ds):
        out.append({"asOf": v.as_of.isoformat() if v.as_of else None, "version": v.version, "rows": v.row_count, "memo": getattr(v, "memo", None) or None,
                    "committedAt": v.committed_at.isoformat() if v.committed_at else None, "owner": v.owner_org, "dataOrigin": v.data_origin})
    out.sort(key=lambda p: (p["asOf"] or "", p["version"]))
    return out


def _period_text(ps: list[dict[str, Any]]) -> str:
    dates = sorted({p["asOf"] for p in ps if p["asOf"]})
    if not dates:
        return "기준일 없음"
    return dates[0] if len(dates) == 1 else f"{dates[0]} ~ {dates[-1]} · {len(dates)}개 기준일"


def _tokens(text: str) -> set[str]:
    from .refine import _tokens as tk

    return tk(text)


def _score(text: str, toks: set[str], d: dict[str, Any]) -> int:
    from .refine import _score as sc

    return sc(toks, text, d)


def graph_context(codes: list[str], max_relations: int = 12) -> dict[str, Any]:
    """Neo4j — 입력 자료의 이웃 관계 · 개념 키 · 같은 개념/지표를 공유하는 다른 자료. 장애면 {'available': False}."""
    from nhdip.graph.neo4j_client import GraphUnavailable, run
    from nhdip.knowledge.query import graph_up, mark_graph_down, mark_graph_ok

    out: dict[str, Any] = {"available": False, "relations": [], "concepts": [], "related": []}
    if not codes:
        out["reason"] = "입력 자료 없음"
        return out
    if not graph_up():
        out["reason"] = "그래프 연결 쉬는 중(최근 장애)"
        return out
    try:
        rows = run(
            "MATCH (d:Dataset)-[r]-(n) WHERE d.key IN $codes AND NOT n:DatasetVersion "
            "RETURN d.key AS src, coalesce(d.name, d.key) AS srcName, type(r) AS rel, startNode(r) = d AS outgoing, labels(n)[0] AS label, n.key AS key, coalesce(n.name, n.key) AS name LIMIT 80",
            codes=codes,
        )
        rel_rows = run(
            "MATCH (d:Dataset)-[]-(m)-[]-(d2:Dataset) WHERE d.key IN $codes AND NOT d2.key IN $codes AND NOT m:DatasetVersion "
            "RETURN d2.key AS key, coalesce(d2.name, d2.key) AS name, collect(DISTINCT coalesce(m.name, m.key))[0..3] AS via, count(DISTINCT m) AS n ORDER BY n DESC LIMIT 10",
            codes=codes,
        )
    except GraphUnavailable as exc:
        mark_graph_down()
        out["reason"] = f"그래프 장애: {str(exc)[:120]}"
        return out
    mark_graph_ok()
    out["available"] = True
    seen: set[tuple[str, str, str]] = set()
    concepts: list[str] = []
    for r in rows:
        key = (str(r.get("src")), str(r.get("rel")), str(r.get("key")))
        if key in seen or not r.get("key"):
            continue
        seen.add(key)
        label = str(r.get("label") or "")
        if label not in STRUCT_LABELS and str(r["key"]) not in concepts:
            concepts.append(str(r["key"]))
        if len(out["relations"]) < max_relations:
            out["relations"].append({"from": r.get("srcName"), "rel": r.get("rel"), "to": r.get("name"), "toLabel": label, "outgoing": bool(r.get("outgoing"))})
    out["concepts"] = concepts[:20]
    out["related"] = [{"code": r["key"], "name": r.get("name"), "via": [str(x) for x in (r.get("via") or [])][:3]} for r in rel_rows if r.get("key")]
    return out


def _latest_values(session: Session, codes: list[str]) -> dict[str, tuple[Any, Any, Any]]:
    """{지표: (최근 값, 직전 값, 기준일)} — calc.metric_value 최근 행."""
    out: dict[str, tuple[Any, Any, Any]] = {}
    for code in codes:
        mv = session.execute(select(MetricValue).where(MetricValue.metric_code == code).order_by(MetricValue.created_at.desc()).limit(1)).scalar()
        if mv is not None:
            out[code] = (mv.display_value if mv.display_value is not None else mv.value, mv.previous_value, mv.as_of)
    return out


def related_kpis(session: Session, spec: dict[str, Any], own_workflow: str | None, limit: int) -> list[dict[str, Any]]:
    """상위 부서 KPI — 명세가 쓴 KPI + 명세 글과 관련 높은 다른 흐름 지표, 모자라면 경영목표 흐름(목표 확정 조건이 있는 흐름) 지표."""
    from .spec import kpi_catalog

    if limit <= 0:
        return []
    used = [str(ref["kpi"]) for m in spec.get("metrics") or [] for ref in (m.get("args") or {}).values() if isinstance(ref, dict) and ref.get("kpi")]
    text = " ".join(str(spec.get(k) or "") for k in ("title", "purpose", "domain_knowledge", "task"))
    toks = {t for t in _tokens(text) if len(t) >= 2}
    goal_wfs = set(session.execute(select(WorkflowTrigger.workflow_code).where(WorkflowTrigger.enabled, WorkflowTrigger.kind == "event", WorkflowTrigger.target == "goal.confirmed")).scalars())
    cat = [k for k in kpi_catalog(session, limit=400, per_workflow=40) if k["workflow"] != own_workflow]
    scored = []
    for i, k in enumerate(cat):
        s = sum(2 for t in _tokens(f"{k['label']} {k['workflowName']}") if t in toks)
        if k["code"] in used:
            s += 100
        scored.append((s, i, k))
    scored.sort(key=lambda x: (-x[0], x[1]))
    picked = [k for s, _, k in scored if s > 0][:limit]
    if len(picked) < min(3, limit):
        for k in cat:
            if k["workflow"] in goal_wfs and k not in picked:
                picked.append(k)
            if len(picked) >= min(3, limit):
                break
    vals = _latest_values(session, [k["code"] for k in picked])
    out = []
    for k in picked:
        v = vals.get(k["code"])
        out.append({**k, "used": k["code"] in used, "value": float(v[0]) if v and v[0] is not None else None, "previous": float(v[1]) if v and v[1] is not None else None,
                    "asOf": v[2].isoformat() if v and v[2] else None})
    return out


def build_context(session: Session, spec: dict[str, Any], team: Team, *, inputs: list[str], own_workflow: str | None = None, use_graph: bool = True) -> dict[str, Any]:
    """팀 데이터 컨텍스트 — 보고서 '참고한 팀 데이터' 절 · 분석 에이전트 입력 · 근거 검색 필터의 원천."""
    from .spec import dataset_catalog

    cfg = settings(session)
    scopes = dataset_scopes(session, team.orgs)
    text = " ".join(str(spec.get(k) or "") for k in ("title", "purpose", "domain_knowledge", "task"))
    toks = _tokens(text)
    graph = graph_context(inputs, cfg["max_relations"]) if use_graph else {"available": False, "reason": "그래프 미사용", "relations": [], "concepts": [], "related": []}
    related = {r["code"]: r for r in graph.get("related") or []}
    cat = {d["code"]: d for d in dataset_catalog(session)}
    cands = []
    for code, d in cat.items():
        sc = scopes.get(code, {"scope": "other", "owners": []})
        if code not in inputs and code not in related and sc["scope"] not in ("team", "common"):
            continue  # 다른 부서 · 전행 자료는 입력이거나 온톨로지로 이어졌을 때만
        if code not in scopes and code not in inputs:
            continue  # 현재 판이 없는 정의
        score = _score(text, toks, d) + SCOPE_BONUS[sc["scope"]] + (3 if code in related else 0)
        cands.append((code in inputs, score, code))
    cands.sort(key=lambda x: (not x[0], -x[1], x[2]))
    picked = [c for c in cands if c[0]] + [c for c in cands if not c[0]][: cfg["max_datasets"]]
    datasets = []
    for is_input, score, code in picked:
        ds = session.get(Dataset, code)
        if ds is None:
            continue
        ps = periods(session, ds)
        sc = scopes.get(code, {"scope": "other", "owners": []})
        datasets.append({
            "code": code, "name": ds.name, "scope": sc["scope"], "scopeLabel": SCOPE_LABEL[sc["scope"]], "use": "input" if is_input else "reference",
            "useLabel": "계산 입력" if is_input else ("온톨로지 연관" if code in related else "참고"), "periods": ps[-12:], "periodText": _period_text(ps),
            "versions": "+".join(str(p["version"]) for p in ps) or "-", "rows": sum(int(p["rows"] or 0) for p in ps), "asOfColumn": ds.as_of_column,
            **({"via": related[code]["via"]} if code in related else {}), "score": score,
        })
    kpis = related_kpis(session, spec, own_workflow, cfg["max_kpis"])
    wf_names = {w.code: w.name for w in session.execute(select(Workflow)).scalars()}
    for k in kpis:
        k["workflowName"] = wf_names.get(k["workflow"], k["workflowName"])
    return {
        "team": team.json(),
        "datasets": datasets,
        "kpis": kpis,
        "graph": {k: graph.get(k) for k in ("available", "reason", "relations", "related")},
        "concepts": graph.get("concepts") or [],
        "counts": {"team": sum(1 for d in datasets if d["scope"] == "team"), "common": sum(1 for d in datasets if d["scope"] == "common"), "inputs": sum(1 for d in datasets if d["use"] == "input")},
    }


def llm_summary(tc: dict[str, Any]) -> dict[str, Any]:
    """분석 에이전트(LLM) 입력용 요약 — 숫자 값은 넣지 않는다(서술 수치는 마커만 · numeric_provenance)."""
    return {
        "team": (tc.get("team") or {}).get("name"),
        "datasets": [{"name": d["name"], "scope": d["scopeLabel"], "use": d["useLabel"], "periods": d["periodText"]} for d in tc.get("datasets") or []][:10],
        "upperKpis": [{"label": k["label"], "workflow": k["workflowName"], "trend": None if k.get("value") is None or k.get("previous") is None else ("up" if k["value"] > k["previous"] else "down" if k["value"] < k["previous"] else "flat")}
                      for k in tc.get("kpis") or []][:8],
        "relations": [f"{r['from']} -{r['rel']}- {r['to']}" for r in ((tc.get("graph") or {}).get("relations") or [])][:12],
    }
