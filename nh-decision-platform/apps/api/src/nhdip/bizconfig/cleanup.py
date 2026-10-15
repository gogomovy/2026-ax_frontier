"""기존 DB 의 예전 시드 업무 구조 정리 (Phase O · BIZ-06 · Q219) — `python -m nhdip.cli remove-seed-structure [--yes]`.

지우는 것: 플랫폼 항목 · 업무 구성 파일이 만든 것 · 분석 에이전트(wf_an_* · dyn_*)가 아닌
지표(계산 값 포함) · 업무 흐름(단계 · 조건 · 화면 연결) · 업무 규칙 · 화면 산출물 · 업무 화면(권한 · 화면 리소스) · 서술 에이전트 ·
지식 컬렉션(문서가 없는 것) · 컬럼 정의서 · 자료가 없는 데이터셋 정의 · 업무 설정 값(플랫폼 기본으로) · 업무 온톨로지 클래스 · 관계 · 별칭 · 조직(사용자 · 하위 조직이 없는 것).
지우는 작업이므로 기본은 미리보기. 먼저 백업(make backup)하고 --yes 로 실행한다.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import delete as sql_delete, func, select, text
from sqlalchemy.orm import Session

from nhdip.events import audit, emit
from nhdip.models import (Agent, AppUser, ColumnContract, Dataset, KbChunk, KbCollection, Metric, OrgUnit, Rule, Screen, ScreenGrant, Setting, ViewArtifact, Workflow, source)

BUSINESS_SETTINGS = ("request.types", "request.to_org", "contracts.dept_prefix", "contracts.raw_depts", "contracts.row_builders", "assist.workflow_resources", "risk.segment_labels",
                     "risk.retail_pool_note", "docs.owner_orgs", "workflow.scopes", "assist.metric_synonyms", "goal.rule_links", "ui.batch_label", "ui.goal_roles", "ui.scopes",
                     "ui.examples", "ui.labels", "ui.notices", "doc_class.labels", "doc_class.default_origin")


def _owned(session: Session) -> dict[str, set[str]]:
    from .apply import active_configs

    out: dict[str, set[str]] = {}
    for c in active_configs(session):
        for k, v in ((c.owned or {}).get("keys") or {}).items():
            out.setdefault(k, set()).update(map(str, v))
    return out


def _analysis(code: str) -> bool:
    return code.startswith(("wf_an_", "dyn_", "an_"))


def plan(session: Session) -> dict[str, Any]:
    from nhdip.seed import defs_core as C
    from nhdip.seed import defs_knowledge as K

    own = _owned(session)
    pf_wf = {w["code"] for w in C.WORKFLOWS_M}
    wfs = [w.code for w in session.execute(select(Workflow).order_by(Workflow.code)).scalars() if w.code not in pf_wf and not _analysis(w.code) and w.code not in own.get("workflows", set())]
    metrics = [m.code for m in session.execute(select(Metric).order_by(Metric.code)).scalars()
               if m.workflow_code in wfs or (m.workflow_code not in pf_wf and not _analysis(m.code) and not _analysis(m.workflow_code) and m.code not in own.get("metrics", set()) and m.workflow_code not in own.get("workflows", set()))]
    pf_rules = {r[0] for r in C.RULES}
    rules = [r.code for r in session.execute(select(Rule).order_by(Rule.code)).scalars() if r.code not in pf_rules and r.code not in own.get("rules", set())]
    keep_out: set[str] = set()
    for w in session.execute(select(Workflow)).scalars():
        if w.code not in wfs:
            keep_out |= set(w.outputs or [])
    arts = sorted({k for (k,) in session.execute(select(ViewArtifact.key).distinct()) if k.split("@")[0] not in keep_out and k.split("@")[0] not in own.get("artifacts", set())
                   and not k.startswith(("report.an_", "contract."))})
    pf_screens = {s["code"] for s in C.SCREENS}
    screens = [s.code for s in session.execute(select(Screen).order_by(Screen.code)).scalars() if s.code not in pf_screens and s.code not in own.get("screens", set())]
    pf_agents = {a[0] for a in C.AGENTS}
    agents = [a.code for a in session.execute(select(Agent).order_by(Agent.code)).scalars() if a.code not in pf_agents and not _analysis(a.code) and a.code not in own.get("agents", set())]
    pf_cols = {c["code"] for c in K.COLLECTIONS}
    cols = []
    for c in session.execute(select(KbCollection).order_by(KbCollection.code)).scalars():
        if c.code in pf_cols or c.code in own.get("collections", set()):
            continue
        docs = session.execute(select(func.count()).select_from(KbChunk).where(KbChunk.collection_code == c.code, KbChunk.source_kind != "artifact")).scalar() or 0
        if not docs:
            cols.append(c.code)
    contracts = [f"{c.table_code}|{c.column_name}" for c in session.execute(select(ColumnContract).order_by(ColumnContract.table_code, ColumnContract.seq)).scalars()
                 if f"{c.table_code}|{c.column_name}" not in own.get("contracts", set())]
    empty_ds = []
    for d in session.execute(select(Dataset).order_by(Dataset.code)).scalars():
        t = source(d.origin)
        if not session.execute(select(t.version.id).where(t.version.dataset_code == d.code).limit(1)).first():
            empty_ds.append(d.code)
    settings = [k for k in BUSINESS_SETTINGS if session.get(Setting, k) is not None and k not in own.get("settings", set())
                and (k not in C.SETTINGS or session.get(Setting, k).value != C.SETTINGS[k][0])]
    pf_orgs = {o[0] for o in C.ORGS}
    orgs = []
    for o in session.execute(select(OrgUnit).order_by(OrgUnit.level.desc(), OrgUnit.code)).scalars():
        if o.code in pf_orgs or o.code in own.get("orgs", set()):
            continue
        users = session.execute(select(func.count()).select_from(AppUser).where(AppUser.org_code == o.code)).scalar() or 0
        orgs.append({"code": o.code, "name": o.name, "users": int(users)})
    from nhdip.graph.proposals import active

    sc = active(session)
    pf_cls = {c["label"] for c in C.ONTOLOGY_CLASSES}
    pf_rel = {r["type"] for r in C.ONTOLOGY_RELATIONS}
    own_on = own.get("ontology", set())
    onto = {"classes": [], "relations": [], "aliases": []}
    if sc is not None:
        onto["classes"] = [c["label"] for c in sc.classes or [] if c.get("label") not in pf_cls and f"class:{c.get('label')}" not in own_on and not c.get("backing")]
        onto["relations"] = [r["type"] for r in sc.relations or [] if r.get("type") not in pf_rel and f"relation:{r.get('type')}" not in own_on and not r.get("backing")]
        onto["aliases"] = [k for k in (sc.aliases or {}) if f"alias:{k}" not in own_on]
    return {"workflows": wfs, "metrics": metrics, "rules": rules, "artifacts": arts, "screens": screens, "agents": agents, "collections": cols, "contracts": contracts,
            "emptyDatasets": empty_ds, "settings": settings, "orgs": orgs, "ontology": onto}


def summary(p: dict[str, Any]) -> dict[str, int]:
    return {k: (len(v) if isinstance(v, list) else sum(len(x) for x in v.values())) for k, v in p.items()}


def execute(session: Session, actor: str = "cli") -> dict[str, Any]:
    from nhdip.seed import defs_core as C

    p = plan(session)
    if p["metrics"]:
        for t in ("calc.metric_value", "calc.calc_run"):
            session.execute(text(f"DELETE FROM {t} WHERE split_part(split_part(metric_code, '#', 1), '@', 1) = ANY(:c)"), {"c": p["metrics"]})
        session.execute(sql_delete(Metric).where(Metric.code.in_(p["metrics"])))
    if p["workflows"]:
        session.execute(sql_delete(Workflow).where(Workflow.code.in_(p["workflows"])))
    if p["rules"]:
        session.execute(sql_delete(Rule).where(Rule.code.in_(p["rules"])))
    for k in p["artifacts"]:
        session.execute(sql_delete(ViewArtifact).where(ViewArtifact.key == k))
        session.execute(sql_delete(KbChunk).where(KbChunk.source_key == k))
    if p["agents"]:
        session.execute(sql_delete(Agent).where(Agent.code.in_(p["agents"])))
    if p["screens"]:
        session.execute(sql_delete(ScreenGrant).where(ScreenGrant.screen_code.in_(p["screens"])))
        session.execute(sql_delete(Screen).where(Screen.code.in_(p["screens"])))
        st = session.get(Setting, "screen.resources")
        if st is not None and isinstance(st.value, dict):
            st.value = {k: v for k, v in st.value.items() if k not in set(p["screens"])}
    for c in p["collections"]:
        session.execute(sql_delete(KbChunk).where(KbChunk.collection_code == c))
        session.execute(sql_delete(KbCollection).where(KbCollection.code == c))
    for x in p["contracts"]:
        t, col = x.split("|", 1)
        session.execute(sql_delete(ColumnContract).where(ColumnContract.table_code == t, ColumnContract.column_name == col))
    for code in p["emptyDatasets"]:
        d = session.get(Dataset, code)
        if d is not None:
            session.delete(d)
    for k in p["settings"]:
        row = session.get(Setting, k)
        if row is None:
            continue
        if k in C.SETTINGS:
            row.value = copy.deepcopy(C.SETTINGS[k][0])
        else:
            session.delete(row)
    session.flush()
    kept = []
    for o in p["orgs"]:
        row = session.get(OrgUnit, o["code"])
        kids = session.execute(select(func.count()).select_from(OrgUnit).where(OrgUnit.parent_code == o["code"])).scalar() or 0
        if row is None or o["users"] or kids:
            kept.append(o)
            continue
        session.execute(sql_delete(ScreenGrant).where(ScreenGrant.org_code == o["code"]))
        session.delete(row)
        session.flush()
    on = p["ontology"]
    if any(on.values()):
        from nhdip.graph.proposals import active, activate_schema

        sc = active(session)
        if sc is not None:
            activate_schema(session, {"classes": [c for c in sc.classes or [] if c.get("label") not in set(on["classes"])],
                                      "relations": [r for r in sc.relations or [] if r.get("type") not in set(on["relations"])],
                                      "aliases": {k: v for k, v in (sc.aliases or {}).items() if k not in set(on["aliases"])}, "interfaces": sc.interfaces or []},
                            note="예전 시드 업무 구조 정리(remove-seed-structure)", actor=actor)
    session.flush()
    emit(session, "config.changed", {"kind": "seed_structure_removed"}, actor)
    out = {**summary(p), "orgsKept": kept}
    audit(session, actor, "admin.seed_structure.remove", "seed", None, {**out, "plan": {k: v for k, v in p.items() if k not in ("metrics", "contracts")}})
    return out
