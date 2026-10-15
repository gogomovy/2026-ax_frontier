"""관리자 [파이프라인] 화면 데이터 (B.39 · PIPE-01~07, 설계 §19.22).

원천(데이터셋 · 문서 분류 · 규칙 · 이벤트 · 정기 실행) → 워크플로우(노드 · 에이전트 · 최근/현재 실행) → 산출물(화면 · 보고서 · mart) → 업무 화면.
연결은 DB 정의(트리거 · 지표/바인딩 계보 · outputs · 적재 노드 설정 · screen.resources)에서만 만든다 — 화면에 코드를 두지 않는다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.models import Agent, Dataset, Job, Metric, Rule, Screen, Setting, ViewArtifact, ViewBinding, Workflow, WorkflowNode, WorkflowRun, WorkflowTrigger, source
from nhdip.models.runtime import NodeRun
from nhdip.seed.defs_core import PIPELINE_STAGES as DEFAULT_STAGES

ETC = {"key": "etc", "label": "기타", "impls": []}


def _iso(v: Any) -> str | None:
    return v.isoformat() if v is not None else None


def _cron_label(expr: str) -> str:
    """'30 6 * * *' → '매일 06:30', '0 6 * * 1-5' → '평일 06:00' — 그 외는 식 그대로."""
    p = expr.split()
    if len(p) == 5 and p[0].isdigit() and p[1].isdigit() and p[2] == "*" and p[3] == "*":
        day = {"*": "매일", "1-5": "평일"}.get(p[4])
        if day:
            return f"{day} {int(p[1]):02d}:{int(p[0]):02d}"
    return expr


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None and s.value is not None else default


def _count(v: Any) -> int | None:
    if isinstance(v, (list, dict)):
        return len(v)
    if isinstance(v, int):
        return v
    return None


def node_summary(impl: str, out: Any, error: str | None = None) -> str:
    """노드 출력 → 한 줄 요약(수치는 출력에 기록된 건수만, 새로 계산하지 않음)."""
    if error:
        return f"오류: {error[:120]}"
    if not isinstance(out, dict):
        return ""
    by = {"llm": "LLM 판단", "rule": "규칙 판단"}.get(str(out.get("by") or ""), "")
    if impl == "load_inputs":
        miss = _count(out.get("missing")) or 0
        return f"데이터셋 {_count(out.get('datasets')) or 0}개 고정" + (f" · 없음 {miss}" if miss else "")
    if impl == "compute_metrics":
        err = _count(out.get("errors")) or 0
        return f"지표 {_count(out.get('computed')) or _count(out.get('values')) or 0}개 계산 · 변경 {_count(out.get('changed')) or 0}" + (f" · 오류 {err}" if err else "")
    if impl == "detect_changes":
        return " · ".join(x for x in (by, f"유의 변화 {_count(out.get('items')) or 0}건") if x)
    if impl == "plan_run":
        skip = " · 서술 건너뜀" if out.get("skip") else ""
        return " · ".join(x for x in (by, f"서술 대상 {_count(out.get('narrate')) or 0}건", f"후속 {_count(out.get('chain')) or 0}") if x) + skip
    if impl == "retrieve_evidence":
        return f"근거 {_count(out.get('hits')) or 0}건 · 거부 {_count(out.get('rejected')) or 0}"
    if impl == "narrate":
        res = [r for r in out.get("results") or [] if isinstance(r, dict)]
        done = [r for r in res if r.get("statement")]
        kept = [r for r in res if r.get("skipped")]
        if done:
            return f"{out.get('model') or 'LLM'} · 서술 {len(done)}/{len(res)}건" + (f" · 유지 {len(kept)}" if kept else "")
        if kept:
            return f"기존 서술 유지 {len(kept)}건(계획상 갱신 대상 아님)"
        return str(out.get("reason") or out.get("plan") or out.get("note") or "서술 대상 없음")[:120]
    if impl == "critic":
        return f"검토 {_count(out.get('reviewed')) or 0}건"
    if impl == "materialize_contracts":
        t = out.get("tables") or {}
        bad = _count(out.get("attention")) or 0
        return f"정의서 표 {len(t)}개 적재" + (f" · 주의 {bad}" if bad else "")
    if impl == "publish":
        return f"산출물 {_count(out.get('published')) or 0}개 게시 · 이벤트 {_count(out.get('events')) or 0}"
    if impl == "build_views":
        return f"표 · 차트 바인딩 {_count(out.get('bindings')) or 0}개 · 수치 {_count(out.get('figures_patched')) or 0}"
    if isinstance(out.get("summary"), str):
        return out["summary"][:120]
    keys = [k for k in out if not k.startswith("_")][:3]
    return " · ".join(f"{k} {_count(out[k])}" for k in keys if _count(out[k]) is not None)


def _agent_info(session: Session, agents: dict[str, Agent], code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    a = agents.get(code)
    if a is None:
        return {"code": code, "name": code, "kind": "unknown", "model": None, "enabled": False}
    model = None
    if a.kind == "llm":
        from nhdip.llm.client import LlmUnavailable, resolve

        try:
            r = resolve(session, code)
            model = r.model if r.base_url else None
        except LlmUnavailable:
            model = None
        except Exception:  # noqa: BLE001 — 표시용
            model = None
    return {"code": a.code, "name": a.name, "kind": a.kind, "model": model, "enabled": a.enabled}


def _datasets_in(obj: Any) -> set[str]:
    from nhdip.graph.projection import _datasets_in_args

    return _datasets_in_args(obj)


def build_pipeline(session: Session) -> dict[str, Any]:
    stages = _setting(session, "pipeline.stages", DEFAULT_STAGES) or DEFAULT_STAGES
    stage_of = {impl: st["key"] for st in stages for impl in st.get("impls") or []}
    agents = {a.code: a for a in session.execute(select(Agent)).scalars()}
    agent_cache: dict[str, Any] = {}

    def agent(code: str | None):
        if code not in agent_cache:
            agent_cache[code] = _agent_info(session, agents, code)
        return agent_cache[code]

    # ── 원천
    sources: dict[str, dict[str, Any]] = {}
    for d in session.execute(select(Dataset).where(Dataset.active).order_by(Dataset.origin, Dataset.code)).scalars():
        t = source(d.origin)
        v = session.execute(select(t.version).where(t.version.dataset_code == d.code, t.version.is_current).order_by(t.version.version.desc()).limit(1)).scalar()
        sources[f"dataset:{d.code}"] = {"id": f"dataset:{d.code}", "kind": "dataset", "code": d.code, "label": d.name, "origin": d.origin, "datasetKind": d.kind,
                                        "version": v.version if v else None, "committedAt": _iso(v.committed_at) if v else None, "rows": v.row_count if v else None,
                                        "dataOrigin": v.data_origin if v else None, "fileName": v.file_name if v else None}
    doc_labels = _setting(session, "doc_class.labels", {}) or {}
    for code, label in doc_labels.items():
        n = 0
        for o in ("bank", "ext"):
            n += session.execute(select(func.count()).select_from(source(o).document).where(source(o).document.is_current, source(o).document.doc_class == code)).scalar() or 0
        sources[f"doc_class:{code}"] = {"id": f"doc_class:{code}", "kind": "doc_class", "code": code, "label": label, "documents": n}
    rules = {r.code: r for r in session.execute(select(Rule)).scalars()}

    def ensure(kind: str, target: str) -> str:
        sid = f"{kind}:{target}"
        if sid not in sources:
            if kind == "rule":
                r = rules.get(target)
                sources[sid] = {"id": sid, "kind": "rule", "code": target, "label": r.name if r else target, "version": r.active_version if r else None}
            elif kind == "cron":
                sources[sid] = {"id": sid, "kind": "cron", "code": target, "label": f"정기 실행 {_cron_label(target)}"}
            elif kind == "any":
                sources[sid] = {"id": sid, "kind": "any", "code": target, "label": {"dataset": "모든 데이터셋 변경", "document": "모든 문서 변경", "ontology": "온톨로지 스키마 변경", "config": "설정 · 정의 변경"}.get(target, f"모든 {target} 변경")}
            elif kind == "setting":
                sources[sid] = {"id": sid, "kind": "setting", "code": target, "label": f"설정 {target}"}
            else:
                sources[sid] = {"id": sid, "kind": "event", "code": target, "label": {"goal.confirmed": "경영목표 확정", "contract.changed": "정의서 변경", "change.detected": "변화 감지"}.get(target, target)}
        return sid

    # 업무 구성(Phase O)은 원천을 자료 이름으로 적는다 — 지금 있는 데이터셋으로 잇고, 없으면 '자료 대기' 칸
    from nhdip.data.sources import Resolver

    res = Resolver(session)

    def ds_node(ref: str) -> str:
        d = res.resolve(ref)
        # 정의만 남고 올린 자료(현재 판)가 없으면 '자료 대기' — 지운 자료의 정의 이름(예전 파일 제목)이 원천으로 남아 보이지 않게
        if d is not None and f"dataset:{d.code}" in sources and sources[f"dataset:{d.code}"]["version"] is not None:
            sources[f"dataset:{d.code}"].setdefault("sourceNames", [])
            if ref != d.code and ref not in sources[f"dataset:{d.code}"]["sourceNames"]:
                sources[f"dataset:{d.code}"]["sourceNames"].append(ref)
            return f"dataset:{d.code}"
        sid = f"waiting:{ref}"
        if sid not in sources:
            sp = res.spec(ref)
            sources[sid] = {"id": sid, "kind": "waiting", "code": ref, "label": f"{ref} (자료 대기)", "columns": sp.columns if sp else [], "config": sp.config_name if sp else None}
        return sid

    from nhdip.bizconfig.apply import active_configs

    owner = {w: c.name for c in active_configs(session) for w in ((c.owned or {}).get("keys") or {}).get("workflows") or []}

    # ── 산출물 · 화면
    res_map = _setting(session, "screen.resources", {}) or {}
    screens = {s.code: s for s in session.execute(select(Screen).where(Screen.active)).scalars() if s.kind in ("flow", "reference")}
    outputs: dict[str, dict[str, Any]] = {}

    def out_node(key: str, kind: str | None = None, label: str | None = None) -> str:
        oid = key if key.startswith("mart:") else f"art:{key}"
        if oid not in outputs:
            k = kind or ("report" if key.startswith("report.") else "artifact")
            sc = []
            for code, resources in res_map.items():
                if code not in screens:
                    continue
                rs = set(resources or [])
                if key in rs or (k == "report" and ("reports" in rs or "analysis_tabs" in rs)):
                    sc.append(code)
            outputs[oid] = {"id": oid, "kind": k, "key": key, "label": label or key, "screens": sorted(sc), "updatedAt": None, "workflowRun": None}
        return oid

    # ── 워크플로우
    metrics_by_wf: dict[str, set[str]] = {}
    for m in session.execute(select(Metric).where(Metric.enabled)).scalars():
        metrics_by_wf.setdefault(m.workflow_code or "", set()).update(_datasets_in(m.args))
    for b in session.execute(select(ViewBinding).where(ViewBinding.enabled)).scalars():
        metrics_by_wf.setdefault(b.workflow_code or "", set()).update(_datasets_in(b.params))
    from nhdip.workflow.engine import workflow_has_data

    flows = []
    for w in session.execute(select(Workflow).order_by(Workflow.sort)).scalars():
        inputs: dict[str, dict[str, Any]] = {}
        for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == w.code, WorkflowTrigger.enabled)).scalars():
            kind = "dataset" if t.kind in ("dataset", "master") else t.kind
            sid = ds_node(t.target) if kind == "dataset" and t.target != "*" else ensure(kind, t.target)
            inputs[sid] = {"source": sid, "via": "trigger", "trigger": t.kind}
        for ds in sorted(metrics_by_wf.get(w.code, set())):
            sid = ds_node(ds)
            if sid not in inputs:
                inputs[sid] = {"source": sid, "via": "lineage"}
        nodes = session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == w.code).order_by(WorkflowNode.seq, WorkflowNode.id)).scalars().all()
        outs = [out_node(k) for k in (w.outputs or [])]
        for n in nodes:
            if n.impl == "materialize_contracts":
                for code in (n.config or {}).get("tables") or []:
                    outs.append(out_node(f"mart:{code}", "mart", f"정의서 {code}"))
            if n.impl == "retrieve_evidence":
                for dc in (n.config or {}).get("doc_classes") or []:
                    sid = f"doc_class:{dc}"
                    if sid in sources and sid not in inputs:
                        inputs[sid] = {"source": sid, "via": "evidence"}
        last = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == w.code, WorkflowRun.status != "running").order_by(WorkflowRun.started_at.desc()).limit(1)).scalar()
        running = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == w.code, WorkflowRun.status == "running").order_by(WorkflowRun.started_at.desc()).limit(1)).scalar()
        jobs = session.execute(select(Job).where(Job.workflow_code == w.code, Job.status.in_(("queued", "running", "approval"))).order_by(Job.run_after)).scalars().all()
        last_nodes = {nr.node_key: nr for nr in session.execute(select(NodeRun).where(NodeRun.workflow_run_id == last.id)).scalars()} if last else {}
        live_nodes = {nr.node_key: nr for nr in session.execute(select(NodeRun).where(NodeRun.workflow_run_id == running.id)).scalars()} if running else {}
        node_json = []
        for n in nodes:
            nr = last_nodes.get(n.key)
            lr = live_nodes.get(n.key)
            out = nr.output if nr else None
            node_json.append({
                "key": n.key, "name": n.name, "impl": n.impl, "stage": stage_of.get(n.impl, "etc"), "enabled": n.enabled, "seq": n.seq,
                "agent": agent(n.agent_code),
                "last": {"status": nr.status, "ms": nr.duration_ms, "summary": node_summary(n.impl, out, nr.error), "by": out.get("by") if isinstance(out, dict) else None,
                         "model": out.get("model") if isinstance(out, dict) else None} if nr else None,
                "live": {"status": lr.status, "ms": lr.duration_ms} if lr else None,
            })
        live = None
        if running:
            done = [n for n in node_json if n["live"]]
            pending = [n for n in node_json if not n["live"] and n["enabled"]]
            live = {"status": "running", "runId": running.id, "startedAt": _iso(running.started_at), "done": len(done), "total": len([n for n in node_json if n["enabled"]]),
                    "currentNode": pending[0]["key"] if pending else None}
        elif jobs:
            live = {"status": jobs[0].status, "runAfter": _iso(jobs[0].run_after)}
        no_data = bool(w.outputs) and not workflow_has_data(session, w)
        if no_data:
            # 이 흐름이 읽는 자료가 없다 — 지난 실행(지운 자료로 돈 것)의 노드 결과 · 산출물 시각을 보여 주지 않는다
            for n in node_json:
                n["last"] = None
        flows.append({
            "code": w.code, "name": w.name, "description": w.description, "enabled": w.enabled, "noData": no_data,
            "config": owner.get(w.code) or ("분석 에이전트" if w.code.startswith("wf_an_") else ("플랫폼 공통" if w.code in ("wf_graph_projection", "wf_ontology_build") else None)),
            "waiting": [i["source"] for i in inputs.values() if i["source"].startswith("waiting:")],
            "inputs": list(inputs.values()), "nodes": node_json, "outputs": list(dict.fromkeys(outs)),
            "lastRun": {"id": last.id, "status": last.status, "startedAt": _iso(last.started_at), "finishedAt": _iso(last.finished_at),
                        "causes": [{"type": c.get("type"), "reasons": c.get("reasons")} for c in (last.causes or [])][-5:],
                        "wallMs": ((last.summary or {}).get("obs") or {}).get("wall_ms")} if last else None,
            "live": live, "jobs": [{"id": j.id, "status": j.status, "runAfter": _iso(j.run_after), "causes": len(j.causes or [])} for j in jobs],
        })
    # 보고서는 'reports' 리소스를 가진 화면 중, 같은 워크플로우의 다른 산출물을 보여 주는 화면으로 좁힌다(부서별 분석 화면)
    for f in flows:
        sib = {sc for o in f["outputs"] if outputs.get(o, {}).get("kind") == "artifact" for sc in outputs[o]["screens"]}
        for o in f["outputs"]:
            out = outputs.get(o)
            if out and out["kind"] == "report" and sib:
                # 보고서 리소스가 없는 부서 화면(영업점 분석 결과 탭 등)은 같은 워크플로우 산출물을 보여 주는 화면으로
                out["screens"] = [sc for sc in out["screens"] if sc in sib] or sorted(sib)
    # 산출물 최근 게시
    keys = [o["key"] for o in outputs.values() if o["kind"] != "mart"] + [f"contract.{o['key'][5:]}" for o in outputs.values() if o["kind"] == "mart"]
    # 자료 없는 흐름만 만드는 산출물 — 값 없는 틀이라 '최근 게시'를 비운다(틀을 다시 게시한 시각이 옛 결과처럼 보이지 않게)
    live_outs = {o for f in flows if not f["noData"] for o in f["outputs"]}
    blank_outs = {o for f in flows if f["noData"] for o in f["outputs"]} - live_outs
    for oid in blank_outs:
        if oid in outputs:
            outputs[oid]["empty"] = True
    if keys:
        for a in session.execute(select(ViewArtifact).where(ViewArtifact.is_current, ViewArtifact.key.in_(keys))).scalars():
            oid = f"mart:{a.key[9:]}" if a.key.startswith("contract.") else f"art:{a.key}"
            if oid in outputs and oid not in blank_outs:
                outputs[oid]["updatedAt"] = _iso(a.created_at)
                outputs[oid]["workflowRun"] = a.workflow_run_id
                p = a.payload if isinstance(a.payload, dict) else {}
                if a.key.startswith("contract."):
                    outputs[oid]["label"] = f"{p.get('table') or '원천 검사'} · {p.get('name') or ''}".strip(" ·")
                    outputs[oid]["rows"] = p.get("rows")
                elif p.get("title"):
                    outputs[oid]["label"] = str(p["title"])[:60]
    used = {i["source"] for f in flows for i in f["inputs"]}
    return {
        "stages": [*stages, ETC],
        "sources": [s for s in sources.values() if s["id"] in used],
        "workflows": flows,
        "outputs": list(outputs.values()),
        "screens": [{"code": s.code, "label": s.label, "path": s.path, "section": s.section} for s in sorted(screens.values(), key=lambda x: x.sort or 0)],
    }
