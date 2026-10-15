"""업무 구성 반영 (Phase O · BIZ-02 · BIZ-05 · Q218) — 미리보기 · 반영 · 새 판 · 삭제.

- 같은 이름 = 같은 구성의 새 판. 이전 판에만 있던 것은 지우고, 바뀐 것만 반영한다.
- 이 구성이 만든 것은 `owned` 에 남긴다. 구성을 지우면 만든 것(계산 값 · 화면 산출물 포함)을 함께 지운다.
- 이미 있는 같은 코드(예전 시드로 들어간 행)는 다른 구성의 것이 아니면 넘겨받아 갱신한다.
- 사용자가 있는 조직 · 문서가 있는 컬렉션은 지우지 않고 알린다.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from sqlalchemy import delete as sql_delete, func, select, text
from sqlalchemy.orm import Session

from nhdip.events import audit, emit
from nhdip.models import (Agent, AppUser, BusinessConfig, ColumnContract, Dataset, KbChunk, KbCollection, LlmProfile, Metric, OrgUnit, Prompt, Rule, RuleVersion, Screen,
                          ScreenGrant, Setting, ViewArtifact, ViewBinding, Workflow, WorkflowNode, WorkflowTrigger, utcnow)

from .bundle import BundleError

ABSENT = "__absent__"
TRIGGER_KINDS = {"dataset", "master", "doc_class", "rule", "event", "any", "cron", "config", "setting"}
KINDS = ("orgs", "screens", "grants", "settings", "rules", "agents", "workflows", "metrics", "bindings", "artifacts", "collections", "ontology", "contracts")
LABELS = {"orgs": "조직", "screens": "화면", "grants": "화면 권한", "settings": "설정", "rules": "규칙", "agents": "서술 에이전트", "workflows": "업무 흐름", "metrics": "지표",
          "bindings": "화면 연결", "artifacts": "화면 틀", "collections": "지식 컬렉션", "ontology": "온톨로지", "contracts": "정의서 열", "sources": "자료"}


# ═════════════════════════ 조회 ═════════════════════════
def active_configs(session: Session) -> list[BusinessConfig]:
    return list(session.execute(select(BusinessConfig).where(BusinessConfig.status == "active").order_by(BusinessConfig.name)).scalars())


def current(session: Session, name: str) -> BusinessConfig | None:
    return session.execute(select(BusinessConfig).where(BusinessConfig.name == name, BusinessConfig.status == "active")).scalars().first()


def _keys(b: dict[str, Any]) -> dict[str, list[Any]]:
    """묶음이 가리키는 항목 키 — 소유 · 충돌 · 지울 것 계산."""
    on = b.get("ontology") or {}
    return {
        "orgs": [o["code"] for o in b.get("orgs") or []],
        "screens": [s["code"] for s in b.get("screens") or []],
        "grants": [f"{g['org']}|{g['screen']}" for g in b.get("grants") or []],
        "settings": [s["key"] for s in b.get("settings") or []],
        "rules": [r["code"] for r in b.get("rules") or []],
        "agents": [a["code"] for a in b.get("agents") or []],
        "workflows": [w["code"] for w in b.get("workflows") or []],
        "metrics": [m["code"] for m in b.get("metrics") or []],
        "bindings": sorted({x["workflow_code"] for x in b.get("bindings") or []}),
        "artifacts": [a["key"] for a in b.get("artifacts") or []],
        "collections": [c["code"] for c in b.get("collections") or []],
        "ontology": [f"class:{c.get('label')}" for c in on.get("classes") or []] + [f"relation:{r.get('type')}" for r in on.get("relations") or []]
                    + [f"alias:{k}" for k in on.get("aliases") or {}] + [f"interface:{i.get('name')}" for i in on.get("interfaces") or []],
        "contracts": [f"{c['table_code']}|{c['column_name']}" for c in b.get("contracts") or []],
    }


def _owner_map(session: Session, exclude_name: str | None = None) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for c in active_configs(session):
        if c.name == exclude_name:
            continue
        for kind, keys in ((c.owned or {}).get("keys") or {}).items():
            for k in keys:
                out[(kind, str(k))] = c.name
    return out


# ═════════════════════════ 검증 ═════════════════════════
def validate(session: Session, b: dict[str, Any]) -> tuple[list[str], list[str]]:
    from nhdip.calc import formulas
    from nhdip.calc.metrics import WHERE_OPS, TOKEN_RE
    from nhdip.contracts.rows import ROW_BUILDERS
    from nhdip.views.builders import BUILDERS
    from nhdip.workflow import engine
    import nhdip.workflow.nodes  # noqa: F401 — 노드 구현 등록
    import nhdip.workflow.agent_nodes  # noqa: F401
    import nhdip.workflow.onto_nodes  # noqa: F401

    errors: list[str] = []
    warns: list[str] = []
    src_names = {str(s.get("name") or "").strip() for s in b.get("sources") or []}
    for s in b.get("sources") or []:
        if not str(s.get("name") or "").strip():
            errors.append("[자료] 이름이 빈 줄이 있습니다")
        elif any(ch in s["name"] for ch in ":|]"):
            errors.append(f"[자료] '{s['name']}' — 이름에 : | ] 는 쓸 수 없습니다(화면 표식에 쓰임)")
        if not s.get("columns"):
            warns.append(f"[자료] '{s.get('name')}' — 필요한 열이 없어 데이터셋 이름이 같은 것만 찾습니다")
    ds_codes = {d for (d,) in session.execute(select(Dataset.code))}

    def ds_ok(ref: Any, where: str) -> None:
        if isinstance(ref, str) and ref not in src_names and ref not in ds_codes and ref != "*":
            errors.append(f"{where}: 자료 '{ref}' 가 [자료] 시트에 없고 데이터셋 코드도 아닙니다")

    wf_codes = {w["code"] for w in b.get("workflows") or []} | {c for (c,) in session.execute(select(Workflow.code))}
    metric_codes = {m["code"] for m in b.get("metrics") or []} | {c for (c,) in session.execute(select(Metric.code))}
    rule_codes = {r["code"] for r in b.get("rules") or []} | {c for (c,) in session.execute(select(Rule.code))}
    agent_codes = {a["code"] for a in b.get("agents") or []} | {c for (c,) in session.execute(select(Agent.code))}
    org_codes = {o["code"] for o in b.get("orgs") or []} | {c for (c,) in session.execute(select(OrgUnit.code))}
    screen_codes = {s["code"] for s in b.get("screens") or []} | {c for (c,) in session.execute(select(Screen.code))}
    art_keys = {a["key"] for a in b.get("artifacts") or []} | {k for (k,) in session.execute(select(ViewArtifact.key).distinct())}

    def check_where(w: Any, where: str) -> None:
        for k, v in (w or {}).items():
            if isinstance(v, dict):
                op = next((o for o in WHERE_OPS if o in v), None)
                if op is None:
                    errors.append(f"{where}: 조건 '{k}' 의 연산자를 알 수 없습니다 — {', '.join(WHERE_OPS)}")
                elif op == "in_dataset":
                    ds_ok(v["in_dataset"].get("dataset"), where)
                    check_where(v["in_dataset"].get("where"), where)

    def check_refs(a: Any, where: str) -> None:
        if isinstance(a, dict):
            if isinstance(a.get("q"), dict):
                ds_ok(a["q"].get("dataset"), where)
                check_where(a["q"].get("where"), where)
            if isinstance(a.get("metric"), str) and a["metric"] not in metric_codes:
                errors.append(f"{where}: 지표 '{a['metric']}' 가 없습니다")
            if isinstance(a.get("rule"), str) and a["rule"] not in rule_codes:
                errors.append(f"{where}: 규칙 '{a['rule']}' 가 없습니다")
            for k, v in a.items():
                if k != "q":
                    check_refs(v, where)
        elif isinstance(a, list):
            for x in a:
                check_refs(x, where)

    seen: set[str] = set()
    for m in b.get("metrics") or []:
        w = f"[지표] {m.get('code')}"
        if not m.get("code"):
            errors.append("[지표] 코드가 빈 줄이 있습니다")
            continue
        if m["code"] in seen:
            errors.append(f"{w}: 코드가 겹칩니다")
        seen.add(m["code"])
        if m.get("formula") not in formulas.REGISTRY:
            errors.append(f"{w}: 산식 '{m.get('formula')}' 이(가) 커널에 없습니다")
        if m.get("workflow_code") not in wf_codes:
            errors.append(f"{w}: 업무 흐름 '{m.get('workflow_code')}' 가 없습니다")
        if not isinstance(m.get("args"), dict):
            errors.append(f"{w}: 입력(JSON)이 객체가 아닙니다")
        else:
            check_refs(m["args"], w)
    for wf in b.get("workflows") or []:
        w = f"[업무흐름] {wf.get('code')}"
        if not wf.get("code"):
            errors.append("[업무흐름] 코드가 빈 줄이 있습니다")
            continue
        for n in wf.get("nodes") or []:
            if n.get("impl") not in engine.NODE_IMPLS:
                errors.append(f"{w} 단계 {n.get('key')}: 구현 '{n.get('impl')}' 이(가) 없습니다")
            if n.get("agent_code") and n["agent_code"] not in agent_codes:
                errors.append(f"{w} 단계 {n.get('key')}: 에이전트 '{n['agent_code']}' 가 없습니다")
            cfg = n.get("config") or {}
            for k in ("dataset",):
                if cfg.get(k):
                    ds_ok(cfg[k], f"{w} 단계 {n.get('key')}")
            for d in cfg.get("datasets") or []:
                ds_ok(d, f"{w} 단계 {n.get('key')}")
        for t in wf.get("triggers") or []:
            if t.get("kind") not in TRIGGER_KINDS:
                errors.append(f"{w}: 조건 종류 '{t.get('kind')}' — {', '.join(sorted(TRIGGER_KINDS))}")
            if t.get("kind") in ("dataset", "master"):
                ds_ok(t.get("target"), w)
            if t.get("kind") == "rule" and t.get("target") not in rule_codes and t.get("target") != "*":
                warns.append(f"{w}: 조건 규칙 '{t.get('target')}' 가 없습니다")
    for i, bd in enumerate(b.get("bindings") or [], start=1):
        w = f"[화면연결] {i}줄 {bd.get('artifact_key')}"
        if bd.get("builder") not in BUILDERS:
            errors.append(f"{w}: 만드는 방법 '{bd.get('builder')}' 이(가) 없습니다")
        if bd.get("workflow_code") not in wf_codes:
            errors.append(f"{w}: 업무 흐름 '{bd.get('workflow_code')}' 가 없습니다")
        if bd.get("artifact_key") not in art_keys:
            warns.append(f"{w}: 화면 틀 '{bd.get('artifact_key')}' 이 없습니다(흐름이 처음 게시할 때 생김)")
        p = bd.get("params") or {}
        for k in ("dataset", "master", "scheme", "score", "ref_dataset"):
            if isinstance(p.get(k), str):
                ds_ok(p[k], w)
        for it in p.get("items") or []:
            for k in ("dataset", "master", "ref_dataset"):
                if isinstance(it, dict) and isinstance(it.get(k), str):
                    ds_ok(it[k], w)
        for wk in ("where", "base_where", "current_where", "master_where"):
            check_where(p.get(wk), w)
    for r in b.get("rules") or []:
        if not r.get("code"):
            errors.append("[규칙] 코드가 빈 줄이 있습니다")
        elif not isinstance(r.get("body"), (dict, list)):
            errors.append(f"[규칙] {r['code']}: 본문(JSON)이 객체 · 목록이 아닙니다")
        elif r.get("merge") and not isinstance(r["body"], dict):
            errors.append(f"[규칙] {r['code']}: '공통 규칙에 더함' 은 본문이 객체여야 합니다")
        elif r.get("merge") and session.get(Rule, r["code"]) is None:
            errors.append(f"[규칙] {r['code']}: 더할 공통 규칙이 없습니다")
    for s in b.get("screens") or []:
        if not str(s.get("path") or "").startswith("/"):
            errors.append(f"[화면] {s.get('code')}: 주소는 / 로 시작")
    for g in b.get("grants") or []:
        if g.get("org") not in org_codes:
            errors.append(f"[화면권한] 조직 '{g.get('org')}' 가 없습니다")
        if g.get("screen") not in screen_codes:
            errors.append(f"[화면권한] 화면 '{g.get('screen')}' 가 없습니다")
    for o in b.get("orgs") or []:
        if o.get("parent_code") and o["parent_code"] not in org_codes:
            errors.append(f"[조직] {o.get('code')}: 상위 조직 '{o['parent_code']}' 가 없습니다")
    for st in b.get("settings") or []:
        if st.get("mode") not in (None, "", "set", "merge"):
            errors.append(f"[설정] {st.get('key')}: 반영은 set · merge")
        if str(st.get("key") or "").startswith("ui.") and (st.get("mode") or "set") == "set":
            from nhdip.ui_config import UiConfigError, validate as ui_validate

            try:
                ui_validate(session, st["key"], st.get("value"))
            except UiConfigError as exc:
                warns.append(f"[설정] {st['key']}: {exc}")
    for c in b.get("contracts") or []:
        bd = c.get("binding") or {}
        if isinstance(bd.get("metric"), str) and bd["metric"] not in metric_codes:
            errors.append(f"[정의서] {c.get('table_code')}.{c.get('column_name')}: 지표 '{bd['metric']}' 가 없습니다")
        for k in ("dataset", "base_ym"):
            if isinstance(bd.get(k), str):
                ds_ok(bd[k], f"[정의서] {c.get('table_code')}.{c.get('column_name')}")
    rb = next((s.get("value") for s in b.get("settings") or [] if s.get("key") == "contracts.row_builders"), None)
    for t, spec in (rb or {}).items() if isinstance(rb, dict) else []:
        if (spec or {}).get("builder") not in ROW_BUILDERS:
            errors.append(f"[설정] contracts.row_builders.{t}: 행 생성기 '{(spec or {}).get('builder')}' 이(가) 없습니다")
        for k, ref in ((spec or {}).get("params") or {}).get("sources", {}).items():
            ds_ok(ref, f"[설정] contracts.row_builders.{t}.sources.{k}")
    # 다른 구성이 가진 항목
    owners = _owner_map(session, exclude_name=b.get("name"))
    for kind, keys in _keys(b).items():
        for k in keys:
            o = owners.get((kind, str(k)))
            if o and not (kind == "settings" and _mode_of(b, k) == "merge") and not (kind == "rules" and _rule_merge(b, k)):
                errors.append(f"[{LABELS[kind]}] {k}: 다른 업무 구성 '{o}' 의 항목입니다 — 그 구성에서 빼거나 코드를 바꾸세요")
    _ = TOKEN_RE
    return errors, warns


def _mode_of(b: dict[str, Any], key: str) -> str:
    return next(((s.get("mode") or "set") for s in b.get("settings") or [] if s.get("key") == key), "set")


def _rule_merge(b: dict[str, Any], code: str) -> bool:
    return any(r.get("code") == code and r.get("merge") for r in b.get("rules") or [])


# ═════════════════════════ 미리보기 ═════════════════════════
def preview(session: Session, b: dict[str, Any]) -> dict[str, Any]:
    from nhdip.data.sources import Resolver

    errors, warns = validate(session, b)
    prev = current(session, b["name"])
    old = ((prev.owned or {}).get("keys") or {}) if prev else {}
    new = _keys(b)
    exists = {
        "orgs": {c for (c,) in session.execute(select(OrgUnit.code))}, "screens": {c for (c,) in session.execute(select(Screen.code))},
        "rules": {c for (c,) in session.execute(select(Rule.code))}, "agents": {c for (c,) in session.execute(select(Agent.code))},
        "workflows": {c for (c,) in session.execute(select(Workflow.code))}, "metrics": {c for (c,) in session.execute(select(Metric.code))},
        "artifacts": {k for (k,) in session.execute(select(ViewArtifact.key).distinct())}, "collections": {c for (c,) in session.execute(select(KbCollection.code))},
        "settings": {k for (k,) in session.execute(select(Setting.key))},
    }
    counts = {}
    for kind in KINDS:
        n = new.get(kind) or []
        o = set(map(str, old.get(kind) or []))
        ex = exists.get(kind, set())
        counts[kind] = {"label": LABELS[kind], "total": len(n), "create": sum(1 for k in n if str(k) not in o and k not in ex), "update": sum(1 for k in n if str(k) in o or k in ex),
                        "remove": len(o - set(map(str, n)))}
    counts["sources"] = {"label": LABELS["sources"], "total": len(b.get("sources") or []), "create": 0, "update": 0, "remove": 0}
    res = Resolver(session, specs=b.get("sources") or [])
    status = res.status()
    return {"name": b["name"], "description": b.get("description") or "", "version": (prev.version + 1) if prev else 1, "replaces": prev.id if prev else None,
            "errors": errors, "warnings": warns, "counts": counts, "sources": status,
            "linked": sum(1 for s in status if s["status"] == "linked"), "waiting": sum(1 for s in status if s["status"] == "waiting")}


# ═════════════════════════ 반영 ═════════════════════════
def apply(session: Session, b: dict[str, Any], *, actor: str, file_name: str | None = None, content: bytes | None = None) -> BusinessConfig:
    errors, warns = validate(session, b)
    if errors:
        raise BundleError(" · ".join(errors[:8]) + (f" 외 {len(errors) - 8}건" if len(errors) > 8 else ""))
    from nhdip.locks import lock

    lock(session, f"bizconfig:{b['name']}")
    prev = current(session, b["name"])
    owned_prev = (prev.owned or {}) if prev else {}
    new_keys = _keys(b)
    owned: dict[str, Any] = {"keys": new_keys, "settings_prev": dict(owned_prev.get("settings_prev") or {}), "settings_merge": {}, "rule_merge": {}, "ontology": {}}
    # 이전 판에만 있던 것부터 지운다
    if prev:
        gone = {k: [x for x in (owned_prev.get("keys") or {}).get(k) or [] if x not in set(new_keys.get(k) or [])] for k in KINDS}
        _remove_items(session, gone, owned_prev, actor, keep_settings=set(new_keys["settings"]))
    report: dict[str, Any] = {}
    report["orgs"] = _apply_orgs(session, b.get("orgs") or [])
    report["screens"] = _apply_screens(session, b.get("screens") or [])
    report["grants"] = _apply_grants(session, b.get("grants") or [], actor)
    report["settings"] = _apply_settings(session, b.get("settings") or [], owned, owned_prev)
    report["rules"] = _apply_rules(session, b.get("rules") or [], owned, owned_prev, actor)
    report["agents"] = _apply_agents(session, b.get("agents") or [], actor)
    report["workflows"] = _apply_workflows(session, b.get("workflows") or [])
    session.flush()
    report["metrics"] = _apply_metrics(session, b.get("metrics") or [])
    report["bindings"] = _apply_bindings(session, b.get("bindings") or [], new_keys["bindings"], owned)
    session.flush()
    report["artifacts"] = _apply_artifacts(session, b.get("artifacts") or [], b.get("bindings") or [])
    report["collections"] = _apply_collections(session, b.get("collections") or [], actor)
    report["ontology"] = _apply_ontology(session, b.get("ontology") or {}, owned, owned_prev, actor, b["name"])
    report["contracts"] = _apply_contracts(session, b.get("contracts") or [])
    session.flush()
    sha = hashlib.sha256(content).hexdigest() if content else None
    if prev:
        prev.status = "superseded"
        session.flush()
    cfg = BusinessConfig(name=b["name"], version=(prev.version + 1) if prev else 1, file_name=file_name, sha256=sha, status="active", content=b, owned=owned,
                         report={"applied": report, "warnings": warns[:50], "appliedAt": utcnow().isoformat()}, uploaded_by=actor)
    session.add(cfg)
    session.flush()
    emit(session, "config.changed", {"kind": "business_config", "code": b["name"], "version": cfg.version}, actor)
    if b.get("contracts"):
        emit(session, "contract.changed", {"reason": f"업무 구성 '{b['name']}' 반영", "tables": sorted({c["table_code"] for c in b["contracts"]})}, actor)
    _rerun(session, [w["code"] for w in b.get("workflows") or []], f"업무 구성 '{b['name']}' 반영", actor)
    audit(session, actor, "admin.business_config.apply", "business_config", str(cfg.id), {"name": b["name"], "version": cfg.version, "file": file_name, "report": report})
    return cfg


def _rerun(session: Session, workflows: list[str], reason: str, actor: str) -> None:
    """올린 자료가 있으면 반영한 흐름을 바로 계산(없으면 자료가 올라올 때 흐름 조건 · 계보로 돈다)."""
    from nhdip.graph.projection import has_uploaded_data

    if not workflows or not has_uploaded_data(session):
        return
    for w in workflows:
        if session.get(Workflow, w) is not None:
            emit(session, "manual", {"workflow": w, "reason": reason}, actor)


def _upsert(session: Session, model: Any, key: Any, values: dict[str, Any]) -> str:
    row = session.get(model, key)
    if row is None:
        session.add(model(**values))
        return "create"
    changed = False
    for k, v in values.items():
        if getattr(row, k) != v:
            setattr(row, k, v)
            changed = True
    return "update" if changed else "same"


def _tally(results: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results:
        out[r] = out.get(r, 0) + 1
    return out


def _apply_orgs(session: Session, orgs: list[dict[str, Any]]) -> dict[str, int]:
    from nhdip.orgs import recompute_levels

    by = {o["code"]: o for o in orgs}
    done: set[str] = set()
    res = []

    def put(o: dict[str, Any]) -> None:
        if o["code"] in done:
            return
        if o.get("parent_code") in by:
            put(by[o["parent_code"]])
        res.append(_upsert(session, OrgUnit, o["code"], {"code": o["code"], "name": o.get("name") or o["code"], "unit_type": o.get("unit_type"), "parent_code": o.get("parent_code"),
                                                          "sort": int(o.get("sort") or 0), "active": True, **({"level": 1} if session.get(OrgUnit, o["code"]) is None else {})}))
        session.flush()
        done.add(o["code"])

    for o in orgs:
        put(o)
    recompute_levels(session)
    return _tally(res)


def _screen_resources(session: Session) -> Setting:
    st = session.get(Setting, "screen.resources")
    if st is None:
        st = Setting(key="screen.resources", value={}, description="화면 → 화면 API 리소스(권한 판정)")
        session.add(st)
        session.flush()
    return st


def _apply_screens(session: Session, screens: list[dict[str, Any]]) -> dict[str, int]:
    res = []
    st = _screen_resources(session)
    cur = dict(st.value or {})
    for s in screens:
        vals = {k: s.get(k) for k in ("code", "path", "label", "section", "kind", "step", "count_key", "match", "sort", "admin_only", "active")}
        vals["kind"] = vals["kind"] or "flow"
        vals["sort"] = int(vals["sort"] or 0)
        vals["admin_only"] = bool(vals["admin_only"])
        vals["active"] = True if vals["active"] is None else bool(vals["active"])
        res.append(_upsert(session, Screen, s["code"], vals))
        cur[s["code"]] = list(s.get("resources") or [])
    st.value = cur
    session.flush()
    return _tally(res)


def _apply_grants(session: Session, grants: list[dict[str, Any]], actor: str) -> dict[str, int]:
    res = []
    for g in grants:
        if session.get(ScreenGrant, (g["org"], g["screen"])) is None:
            session.add(ScreenGrant(org_code=g["org"], screen_code=g["screen"], granted_by=actor))
            res.append("create")
        else:
            res.append("same")
    session.flush()
    return _tally(res)


def _apply_settings(session: Session, settings: list[dict[str, Any]], owned: dict[str, Any], owned_prev: dict[str, Any]) -> dict[str, int]:
    res = []
    prev_merge = owned_prev.get("settings_merge") or {}
    for s in settings:
        key, val, mode = s["key"], copy.deepcopy(s.get("value")), s.get("mode") or "set"
        row = session.get(Setting, key)
        if mode == "set":
            if key not in owned["settings_prev"]:
                owned["settings_prev"][key] = copy.deepcopy(row.value) if row is not None else ABSENT
            if row is None:
                session.add(Setting(key=key, value=val, description=s.get("description") or ""))
                res.append("create")
            elif row.value != val:
                row.value = val
                res.append("update")
            else:
                res.append("same")
            continue
        # merge — 사전은 키를 더하고(이전 값 기억), 목록은 없는 항목만 덧붙인다
        rec: dict[str, Any] = dict(prev_merge.get(key) or {})
        if row is None:
            row = Setting(key=key, value={} if isinstance(val, dict) else [], description=s.get("description") or "")
            session.add(row)
            rec["__created__"] = True
        cur = copy.deepcopy(row.value)
        if isinstance(val, dict) and isinstance(cur, dict):
            subs = dict(rec.get("subs") or {})
            for k, v in val.items():
                if k not in subs:
                    subs[k] = copy.deepcopy(cur.get(k, ABSENT))
                cur[k] = v
            rec["subs"] = subs
        elif isinstance(val, list) and isinstance(cur, list):
            items = list(rec.get("items") or [])
            for v in val:
                if v not in cur:
                    cur.append(v)
                    items.append(v)
            rec["items"] = items
        else:
            raise BundleError(f"[설정] {key}: merge 는 지금 값과 같은 형식(사전 · 목록)이어야 합니다")
        res.append("update" if cur != row.value else "same")
        row.value = cur
        owned["settings_merge"][key] = rec
    session.flush()
    return _tally(res)


def _new_rule_version(session: Session, rule: Rule, body: Any, note: str, actor: str) -> None:
    last = session.execute(select(func.max(RuleVersion.version)).where(RuleVersion.rule_code == rule.code)).scalar() or 0
    session.add(RuleVersion(rule_code=rule.code, version=last + 1, body=body, note=note[:200], created_by=actor))
    rule.active_version = last + 1
    session.flush()
    emit(session, "rule.changed", {"rule": rule.code, "version": last + 1}, actor)


def _active_body(session: Session, rule: Rule) -> Any:
    rv = session.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
    return copy.deepcopy(rv.body) if rv else {}


def _apply_rules(session: Session, rules: list[dict[str, Any]], owned: dict[str, Any], owned_prev: dict[str, Any], actor: str) -> dict[str, int]:
    res = []
    for r in rules:
        code = r["code"]
        row = session.get(Rule, code)
        if r.get("merge"):
            body = _active_body(session, row)
            prev_rec = (owned_prev.get("rule_merge") or {}).get(code) or {}
            for k, sub in list(prev_rec.items()):  # 이전 판이 더한 것은 빼고 다시 더한다
                if isinstance(body.get(k), dict):
                    for sk in sub:
                        body[k].pop(sk, None)
            rec: dict[str, list[str]] = {}
            for k, v in (r.get("body") or {}).items():
                if isinstance(v, dict):
                    body[k] = {**(body.get(k) or {}), **v} if isinstance(body.get(k), dict) else dict(v)
                    rec[k] = list(v)
                else:
                    body[k] = v
            owned["rule_merge"][code] = rec
            if body != _active_body(session, row):
                _new_rule_version(session, row, body, "업무 구성 반영(더함)", actor)
                res.append("update")
            else:
                res.append("same")
            continue
        if row is None:
            row = Rule(code=code, name=r.get("name") or code, kind=r.get("kind") or "threshold", description=r.get("description") or "", active_version=1)
            session.add(row)
            session.flush()
            session.add(RuleVersion(rule_code=code, version=1, body=r["body"], note="업무 구성", created_by=actor))
            session.flush()
            res.append("create")
            continue
        row.name, row.kind, row.description = r.get("name") or row.name, r.get("kind") or row.kind, r.get("description") or row.description
        if _active_body(session, row) != r["body"]:
            _new_rule_version(session, row, r["body"], "업무 구성 반영", actor)
            res.append("update")
        else:
            res.append("same")
    return _tally(res)


def _apply_agents(session: Session, agents: list[dict[str, Any]], actor: str) -> dict[str, int]:
    res = []
    profiles = {p.name: p.id for p in session.execute(select(LlmProfile)).scalars()}
    for a in agents:
        vals = {"code": a["code"], "name": a.get("name") or a["code"], "role": a.get("role") or "", "kind": a.get("kind") or "llm", "group_code": a.get("group_code"),
                "profile_id": profiles.get(a.get("profile") or "default")}
        row = session.get(Agent, a["code"])
        if row is None:
            session.add(Agent(**vals, override={}, enabled=True))
            res.append("create")
        else:
            for k, v in vals.items():
                setattr(row, k, v)
            res.append("update")
        session.flush()
        system = a.get("system") or ""
        last = session.execute(select(Prompt).where(Prompt.agent_code == a["code"]).order_by(Prompt.version.desc()).limit(1)).scalar()
        if system and (last is None or last.system != system or (last.user_template or "") != (a.get("user_template") or "")):
            session.add(Prompt(agent_code=a["code"], version=(last.version + 1) if last else 1, system=system, user_template=a.get("user_template") or "", note="업무 구성", created_by=actor))
    session.flush()
    return _tally(res)


def _apply_workflows(session: Session, workflows: list[dict[str, Any]]) -> dict[str, int]:
    res = []
    for w in workflows:
        res.append(_upsert(session, Workflow, w["code"], {"code": w["code"], "name": w.get("name") or w["code"], "description": w.get("description") or "", "outputs": list(w.get("outputs") or []),
                                                          "sort": int(w.get("sort") or 0), "enabled": True if w.get("enabled") is None else bool(w["enabled"])}))
        session.flush()
        old_t = {(t.kind, t.target): t.last_fired_at for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == w["code"])).scalars()}
        session.execute(sql_delete(WorkflowNode).where(WorkflowNode.workflow_code == w["code"]))
        session.execute(sql_delete(WorkflowTrigger).where(WorkflowTrigger.workflow_code == w["code"]))
        for i, n in enumerate(w.get("nodes") or [], start=1):
            session.add(WorkflowNode(workflow_code=w["code"], seq=int(n.get("seq") or i * 10), key=n["key"], name=n.get("name") or n["key"], impl=n["impl"], agent_code=n.get("agent_code"),
                                     enabled=True if n.get("enabled") is None else bool(n["enabled"]), config=n.get("config") or {}))
        for t in w.get("triggers") or []:
            session.add(WorkflowTrigger(workflow_code=w["code"], kind=t["kind"], target=str(t.get("target") or "*"), debounce_sec=t.get("debounce_sec"),
                                        enabled=True if t.get("enabled") is None else bool(t["enabled"]), last_fired_at=old_t.get((t["kind"], str(t.get("target") or "*")))))
    session.flush()
    return _tally(res)


METRIC_FIELDS = ("label", "formula", "args", "unit", "decimals", "rounding", "scale", "workflow_code", "figure_ids", "description", "enabled", "sort")


def _apply_metrics(session: Session, metrics: list[dict[str, Any]]) -> dict[str, int]:
    res = []
    for m in metrics:
        vals = {"code": m["code"], **{k: m.get(k) for k in METRIC_FIELDS}}
        vals["label"] = vals["label"] or m["code"]
        vals["unit"] = vals["unit"] or "NONE"
        vals["figure_ids"] = list(vals["figure_ids"] or [])
        vals["description"] = vals["description"] or ""
        vals["enabled"] = True if vals["enabled"] is None else bool(vals["enabled"])
        vals["sort"] = int(vals["sort"] or 0)
        res.append(_upsert(session, Metric, m["code"], vals))
    session.flush()
    return _tally(res)


def _apply_bindings(session: Session, bindings: list[dict[str, Any]], workflows: list[str], owned: dict[str, Any]) -> dict[str, int]:
    """화면 연결은 흐름 단위로 바꾼다 — 이 구성의 흐름에 있던 연결을 모두 지우고 새로 넣는다."""
    if workflows:
        session.execute(sql_delete(ViewBinding).where(ViewBinding.workflow_code.in_(workflows)))
    for bd in bindings:
        session.add(ViewBinding(workflow_code=bd["workflow_code"], artifact_key=bd["artifact_key"], path=bd["path"], builder=bd["builder"], params=bd.get("params") or {},
                                enabled=True if bd.get("enabled") is None else bool(bd["enabled"])))
    session.flush()
    return {"create": len(bindings)}


def _apply_artifacts(session: Session, artifacts: list[dict[str, Any]], bindings: list[dict[str, Any]]) -> dict[str, int]:
    """화면 틀(값 없는 0세대) — 처음이거나 틀 모양이 바뀐 것만 게시한다(계산된 값이 있는 화면을 이유 없이 비우지 않게)."""
    from nhdip.views.store import get_current, publish
    from nhdip.views.template import to_template

    res = []
    for a in artifacts:
        mine = [bd for bd in bindings if bd.get("artifact_key") == a["key"]]
        tpl = to_template(a["key"], copy.deepcopy(a["payload"]), mine)
        cur = get_current(session, a["key"])
        if cur is None:
            publish(session, a["key"], tpl, produced_by="business_config")
            res.append("create")
        elif json.dumps(to_template(a["key"], copy.deepcopy(cur), mine), sort_keys=True, ensure_ascii=False, default=str) != json.dumps(tpl, sort_keys=True, ensure_ascii=False, default=str):
            publish(session, a["key"], tpl, produced_by="business_config")
            res.append("update")
        else:
            res.append("same")
    return _tally(res)


def publish_templates(session: Session) -> int:
    """활성 구성의 화면 틀을 다시 게시 — 자료 비우기(reset-data) 뒤 값 없는 틀로 되돌릴 때."""
    from nhdip.views.store import publish
    from nhdip.views.template import to_template

    n = 0
    for cfg in active_configs(session):
        b = cfg.content or {}
        for a in b.get("artifacts") or []:
            mine = [bd for bd in b.get("bindings") or [] if bd.get("artifact_key") == a["key"]]
            publish(session, a["key"], to_template(a["key"], copy.deepcopy(a["payload"]), mine), produced_by="business_config")
            n += 1
    return n


COLLECTION_FIELDS = ("label", "description", "kind", "owner_orgs", "shared_orgs", "required_resources", "audience", "sources", "boost", "enabled", "sort")


def _apply_collections(session: Session, cols: list[dict[str, Any]], actor: str) -> dict[str, int]:
    res = []
    for c in cols:
        vals = {"code": c["code"], **{k: c.get(k) for k in COLLECTION_FIELDS}, "updated_by": actor}
        for k, d in (("label", c["code"]), ("description", ""), ("kind", "document"), ("owner_orgs", []), ("shared_orgs", []), ("required_resources", []), ("audience", "restricted"),
                     ("sources", {}), ("boost", 0.0), ("enabled", True), ("sort", 0)):
            if vals[k] is None:
                vals[k] = d
        res.append(_upsert(session, KbCollection, c["code"], vals))
    session.flush()
    return _tally(res)


def _apply_ontology(session: Session, on: dict[str, Any], owned: dict[str, Any], owned_prev: dict[str, Any], actor: str, name: str) -> dict[str, int]:
    from nhdip.graph.proposals import active, activate_schema

    sc = active(session)
    if sc is None or not any(on.get(k) for k in ("classes", "relations", "aliases", "interfaces")):
        return {}
    base = {"classes": copy.deepcopy(sc.classes or []), "relations": copy.deepcopy(sc.relations or []), "aliases": copy.deepcopy(sc.aliases or {}), "interfaces": copy.deepcopy(sc.interfaces or [])}
    new = _without_ontology(base, owned_prev.get("ontology") or {})
    labels = {c.get("label") for c in on.get("classes") or []}
    new["classes"] = [c for c in new["classes"] if c.get("label") not in labels] + list(on.get("classes") or [])
    types = {r.get("type") for r in on.get("relations") or []}
    new["relations"] = [r for r in new["relations"] if r.get("type") not in types] + list(on.get("relations") or [])
    alias_keys: dict[str, list[str]] = {}
    for cls, m in (on.get("aliases") or {}).items():
        cur = dict(new["aliases"].get(cls) or {})
        for k, v in (m or {}).items():
            cur[k] = sorted({*(cur.get(k) or []), *v}) if isinstance(v, list) else v
        new["aliases"][cls] = cur
        alias_keys[cls] = list(m or {})
    names = {i.get("name") for i in on.get("interfaces") or []}
    new["interfaces"] = [i for i in new["interfaces"] if i.get("name") not in names] + list(on.get("interfaces") or [])
    owned["ontology"] = {"classes": sorted(x for x in labels if x), "relations": sorted(x for x in types if x), "aliases": alias_keys, "interfaces": sorted(x for x in names if x)}
    if json.dumps(new, sort_keys=True, ensure_ascii=False) == json.dumps(base, sort_keys=True, ensure_ascii=False):
        return {"same": 1}
    v = activate_schema(session, new, note=f"업무 구성 '{name}' 반영", actor=actor)
    return {"update": 1, "version": v}


def _without_ontology(s: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(s)
    out["classes"] = [c for c in out["classes"] if c.get("label") not in set(rec.get("classes") or [])]
    out["relations"] = [r for r in out["relations"] if r.get("type") not in set(rec.get("relations") or [])]
    for cls, keys in (rec.get("aliases") or {}).items():
        cur = dict(out["aliases"].get(cls) or {})
        for k in keys:
            cur.pop(k, None)
        if cur:
            out["aliases"][cls] = cur
        else:
            out["aliases"].pop(cls, None)
    out["interfaces"] = [i for i in out["interfaces"] if i.get("name") not in set(rec.get("interfaces") or [])]
    return out


CONTRACT_FIELDS = ("table_name", "dept", "seq", "kor_name", "is_pk", "data_type", "source_desc", "source_column", "is_mock", "expected_text", "binding", "active", "workbook")


def _apply_contracts(session: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    res = []
    have = {(c.table_code, c.column_name): c for c in session.execute(select(ColumnContract)).scalars()}
    for r in rows:
        vals = {k: r.get(k) for k in CONTRACT_FIELDS}
        vals["binding"] = vals["binding"] or {}
        vals["is_pk"], vals["is_mock"] = bool(vals["is_pk"]), bool(vals["is_mock"])
        vals["active"] = True if vals["active"] is None else bool(vals["active"])
        vals["seq"] = int(vals["seq"] or 0)
        cur = have.get((r["table_code"], r["column_name"]))
        if cur is None:
            session.add(ColumnContract(table_code=r["table_code"], column_name=r["column_name"], **vals))
            res.append("create")
        else:
            changed = False
            for k, v in vals.items():
                if getattr(cur, k) != v:
                    setattr(cur, k, v)
                    changed = True
            res.append("update" if changed else "same")
    session.flush()
    return _tally(res)


# ═════════════════════════ 삭제 ═════════════════════════
def remove(session: Session, cfg: BusinessConfig, *, actor: str, reason: str) -> dict[str, Any]:
    """구성을 지우면 만든 것을 함께 지운다(계산 값 · 화면 산출물 포함). 사용자가 있는 조직 · 문서가 있는 컬렉션은 남긴다."""
    if cfg.status != "active":
        raise BundleError("이미 지운(또는 새 판으로 바뀐) 구성입니다")
    from nhdip.locks import lock

    lock(session, f"bizconfig:{cfg.name}")
    owned = cfg.owned or {}
    out = _remove_items(session, owned.get("keys") or {}, owned, actor)
    cfg.status = "removed"
    cfg.report = {**(cfg.report or {}), "removed": out, "removedAt": utcnow().isoformat(), "removedBy": actor, "reason": reason}
    session.flush()
    emit(session, "config.changed", {"kind": "business_config", "code": cfg.name, "deleted": True}, actor)
    audit(session, actor, "admin.business_config.remove", "business_config", str(cfg.id), {"name": cfg.name, "version": cfg.version, "reason": reason, "removed": out})
    return out


def _remove_items(session: Session, keys: dict[str, list[Any]], owned: dict[str, Any], actor: str, keep_settings: set[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    keep_settings = keep_settings or set()
    wfs = [w for w in keys.get("workflows") or [] if session.get(Workflow, w) is not None]
    metrics = list(keys.get("metrics") or [])
    if wfs:
        metrics += [c for (c,) in session.execute(select(Metric.code).where(Metric.workflow_code.in_(wfs)))]
    metrics = sorted(set(metrics))
    if metrics:
        # 이 지표로 계산된 값 · 계산 기록 (범위 실행 '<코드>@<지점>' 포함)
        for t in ("calc.metric_value", "calc.calc_run"):
            session.execute(text(f"DELETE FROM {t} WHERE split_part(split_part(metric_code, '#', 1), '@', 1) = ANY(:c)"), {"c": metrics})
        session.execute(sql_delete(Metric).where(Metric.code.in_(metrics)))
    out["metrics"] = len(metrics)
    for bw in keys.get("bindings") or []:
        if bw not in wfs:
            session.execute(sql_delete(ViewBinding).where(ViewBinding.workflow_code == bw))
    if wfs:
        session.execute(sql_delete(Workflow).where(Workflow.code.in_(wfs)))  # 단계 · 조건 · 화면 연결 · 지표는 CASCADE
    out["workflows"] = len(wfs)
    arts = list(keys.get("artifacts") or [])
    n_art = 0
    for k in arts:
        n_art += session.execute(sql_delete(ViewArtifact).where((ViewArtifact.key == k) | ViewArtifact.key.like(f"{k}@%"))).rowcount or 0
        session.execute(sql_delete(KbChunk).where((KbChunk.source_key == k) | KbChunk.source_key.like(f"{k}@%")))
    out["artifacts"] = n_art
    rules = [r for r in keys.get("rules") or [] if r not in (owned.get("rule_merge") or {})]
    if rules:
        session.execute(sql_delete(Rule).where(Rule.code.in_(rules)))
    for code, rec in (owned.get("rule_merge") or {}).items():
        if code not in set(keys.get("rules") or []):
            continue
        row = session.get(Rule, code)
        if row is None:
            continue
        body = _active_body(session, row)
        for k, subs in rec.items():
            if isinstance(body.get(k), dict):
                for sk in subs:
                    body[k].pop(sk, None)
        _new_rule_version(session, row, body, "업무 구성 삭제(더한 것 뺌)", actor)
    out["rules"] = len(keys.get("rules") or [])
    ag = list(keys.get("agents") or [])
    if ag:
        session.execute(sql_delete(Agent).where(Agent.code.in_(ag)))
    out["agents"] = len(ag)
    for g in keys.get("grants") or []:
        org, scr = str(g).split("|", 1)
        session.execute(sql_delete(ScreenGrant).where(ScreenGrant.org_code == org, ScreenGrant.screen_code == scr))
    scr = list(keys.get("screens") or [])
    if scr:
        session.execute(sql_delete(Screen).where(Screen.code.in_(scr)))
        st = session.get(Setting, "screen.resources")
        if st is not None and isinstance(st.value, dict):
            st.value = {k: v for k, v in st.value.items() if k not in set(scr)}
    out["screens"] = len(scr)
    for key in keys.get("settings") or []:
        if key in keep_settings:
            continue
        row = session.get(Setting, key)
        mrec = (owned.get("settings_merge") or {}).get(key)
        if mrec is not None and row is not None:
            cur = copy.deepcopy(row.value)
            if isinstance(cur, dict):
                for k, prev in (mrec.get("subs") or {}).items():
                    if prev == ABSENT:
                        cur.pop(k, None)
                    else:
                        cur[k] = prev
            elif isinstance(cur, list):
                cur = [x for x in cur if x not in (mrec.get("items") or [])]
            if mrec.get("__created__") and not cur:
                session.delete(row)
            else:
                row.value = cur
            continue
        prev = (owned.get("settings_prev") or {}).get(key, ABSENT)
        if row is not None:
            if prev == ABSENT:
                session.delete(row)
            else:
                row.value = prev
    kept_cols = []
    for c in keys.get("collections") or []:
        has = session.execute(select(func.count()).select_from(KbChunk).where(KbChunk.collection_code == c, KbChunk.source_kind != "artifact")).scalar() or 0
        if has:
            kept_cols.append(c)
            continue
        session.execute(sql_delete(KbChunk).where(KbChunk.collection_code == c))
        session.execute(sql_delete(KbCollection).where(KbCollection.code == c))
    out["collectionsKept"] = kept_cols
    rows = [str(x).split("|", 1) for x in keys.get("contracts") or []]
    for t, col in rows:
        session.execute(sql_delete(ColumnContract).where(ColumnContract.table_code == t, ColumnContract.column_name == col))
    out["contracts"] = len(rows)
    if rows:
        emit(session, "contract.changed", {"reason": "업무 구성 삭제", "tables": sorted({t for t, _ in rows})}, actor)
    rec = owned.get("ontology") or {}
    if any(rec.get(k) for k in ("classes", "relations", "aliases", "interfaces")) and keys.get("ontology"):
        from nhdip.graph.proposals import active, activate_schema

        sc = active(session)
        if sc is not None:
            base = {"classes": sc.classes or [], "relations": sc.relations or [], "aliases": sc.aliases or {}, "interfaces": sc.interfaces or []}
            activate_schema(session, _without_ontology(base, rec), note="업무 구성 삭제", actor=actor)
    kept_orgs = []
    orgs = list(keys.get("orgs") or [])
    for code in sorted(orgs, key=lambda c: -(session.get(OrgUnit, c).level if session.get(OrgUnit, c) else 0)):
        o = session.get(OrgUnit, code)
        if o is None:
            continue
        users = session.execute(select(func.count()).select_from(AppUser).where(AppUser.org_code == code)).scalar() or 0
        kids = session.execute(select(func.count()).select_from(OrgUnit).where(OrgUnit.parent_code == code)).scalar() or 0
        if users or kids:
            kept_orgs.append({"code": code, "users": int(users), "children": int(kids)})
            continue
        session.execute(sql_delete(ScreenGrant).where(ScreenGrant.org_code == code))
        session.delete(o)
        session.flush()
    out["orgsKept"] = kept_orgs
    session.flush()
    return out
