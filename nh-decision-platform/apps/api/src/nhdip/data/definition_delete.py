"""데이터셋 정의 삭제 — 연결까지 함께 (Phase M 후속 · 요구사항 DOB-12 · Q208).

정의만 지우는 기존 삭제(DELETE /admin/datasets/{code})는 이 정의를 쓰는 곳(버전 · 지표 · 화면 바인딩 · 트리거)이 남아 있으면 막는다.
시드가 넣은 업무 화면 연결 정의는 늘 지표 · 바인딩이 읽으므로 화면에서 지울 방법이 없었다. 여기서는 확인을 받고 연결까지 함께 정리한다.

  올라온 버전   모두 삭제(버전 삭제와 같은 경로 — 행 · 원본 파일 · 그래프 · 지난 산출물 세대, 삭제 표시 기록은 정의와 함께 지움)
  지표          이 자료를 읽는 지표와 그 지표를 이어 쓰는 파생 지표를 '끔'(enabled=false) — 지우지 않는다(되살리기 = [지표]에서 켬)
  화면 바인딩   이 자료를 읽는 바인딩을 '끔'
  트리거        이 자료를 기다리는 워크플로 트리거(dataset · master)를 지움 — 다시 이으려면 [연결 도우미]
  온톨로지      객체 · 링크 유형의 원천(backing)에서 이 자료를 뺀 새 판(유형은 남김), 이 자료를 원천으로 쓰는 승인 대기 제안은 닫음 (M.23)
  계산된 값     화면 산출물의 수치 · 서술 · 표/차트, 지난 세대, 계산 기록(calc), 실행 기록의 계산 값에서 지움 (M.23 · DOB-14) —
                지표를 끄기만 하면 다음 계산이 그 수치를 건드리지 않아 지운 자료로 낸 옛 값이 화면에 그대로 남았다
  처리 중 요청  승인 대기 · 초안 요청이 있으면 막는다(먼저 반려 · 버림)
현재 버전이 있었고 다른 자료가 남아 있으면 연결이 끊긴 워크플로를 한 번 다시 돌린다. 올린 자료가 하나도 남지 않으면 모든 화면을 값 없는 틀로 둔다.
구성 지도 · 그래프는 꺼진 지표 · 워크플로를 넣지 않고, 자료가 없으면 비어 있다(graph.projection.collect_graph).
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.events import audit, emit
from nhdip.models import Dataset, Metric, Setting, UploadRequest, ViewBinding, Workflow, WorkflowTrigger, source, utcnow

from .deletion import DELETED, DeleteError, clean_reason, delete_dataset_version

log = logging.getLogger(__name__)
SUPPRESSED = "seed.suppressed_datasets"
BASE_WORKFLOWS = {"wf_graph_projection", "wf_ontology_build"}  # 모든 자료를 읽는 기반 워크플로 — 정의 변경 이벤트로 따로 돈다


def _datasets_in(obj: Any) -> set[str]:
    from nhdip.graph.projection import _datasets_in_args

    return _datasets_in_args(obj)


def metric_closure(metrics: list[Metric], code: str | set[str]) -> tuple[list[str], list[str]]:
    """(이 자료를 바로 읽는 지표, 그 지표를 {"metric": X} 로 이어 쓰는 파생 지표). code = 데이터셋 코드 또는 이 자료를 가리키는 이름 집합."""
    names = {code} if isinstance(code, str) else set(code)
    direct = {m.code for m in metrics if names & _datasets_in(m.args)}
    chosen = set(direct)
    grew = True
    while grew:
        grew = False
        for m in metrics:
            if m.code not in chosen and any(isinstance(r, dict) and r.get("metric") in chosen for r in (m.args or {}).values()):
                chosen.add(m.code)
                grew = True
    return sorted(direct), sorted(chosen - direct)


@dataclass
class Links:
    code: str
    versions: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)  # 켜져 있는 것만(끌 대상)
    metric_codes: list[str] = field(default_factory=list)  # 이 자료로 계산되는 지표 전부(꺼진 것 포함) — 화면 · 계산 기록의 값을 지울 대상
    bindings: list[dict[str, Any]] = field(default_factory=list)
    binding_ids: list[int] = field(default_factory=list)  # 이 자료를 읽는 바인딩 전부(꺼진 것 포함)
    proposals: list[int] = field(default_factory=list)  # 이 자료를 원천으로 쓰는 승인 대기 온톨로지 제안
    triggers: list[dict[str, Any]] = field(default_factory=list)
    ontology: list[str] = field(default_factory=list)
    contracts: int = 0
    pending: int = 0
    workflows: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_current(self) -> bool:
        return any(v["isCurrent"] for v in self.versions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "versions": self.versions,
            "rows": sum(int(v.get("rows") or 0) for v in self.versions),
            "metrics": self.metrics,
            "bindings": self.bindings,
            "triggers": self.triggers,
            "ontology": self.ontology,
            "proposals": len(self.proposals),
            "contracts": self.contracts,
            "pending": self.pending,
            "workflows": self.workflows,
            "blocked": f"처리 중인 자료 등록 · 요청 {self.pending}건 — [자료 승인]에서 먼저 반려하거나 버리세요" if self.pending else None,
        }


def links(session: Session, ds: Dataset) -> Links:
    """지우면 함께 정리되는 것 — 미리보기와 실행이 같은 목록을 쓴다."""
    from nhdip.graph.projection import active_schema
    from nhdip.models import ColumnContract

    code = ds.code
    t = source(ds.origin)
    out = Links(code)
    for v in session.execute(select(t.version).where(t.version.dataset_code == code, t.version.status != DELETED).order_by(t.version.version)).scalars():
        out.versions.append({"id": v.id, "version": v.version, "asOf": v.as_of.isoformat() if v.as_of else None, "isCurrent": bool(v.is_current), "rows": int(v.row_count or 0), "status": v.status})
    from nhdip.data.sources import Resolver

    # 업무 구성(Phase O)은 자료 이름으로 원천을 가리킨다 — 그 지표 · 바인딩의 값은 지우되 끄지 않는다(구성은 남고 '자료 대기'가 된다).
    # 데이터셋 코드를 직접 적은 것(분석 에이전트 등)만 예전처럼 끈다.
    names = Resolver(session).refs_for(code)
    metrics = list(session.execute(select(Metric)).scalars())
    direct, derived = metric_closure(metrics, code)
    a_direct, a_derived = metric_closure(metrics, names)
    by_code = {m.code: m for m in metrics}
    out.metric_codes = sorted(set(a_direct + a_derived))
    for c in direct + derived:
        m = by_code[c]
        if m.enabled:
            out.metrics.append({"code": c, "label": m.label, "workflow": m.workflow_code, "derived": c in derived})
    for b in session.execute(select(ViewBinding).order_by(ViewBinding.id)).scalars():
        refs = _datasets_in(b.params)
        if names & refs:
            out.binding_ids.append(b.id)
            if b.enabled and code in refs:
                out.bindings.append({"id": b.id, "workflow": b.workflow_code, "builder": b.builder, "artifact": b.artifact_key, "path": b.path})
    for tr in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.kind.in_(["dataset", "master"]), WorkflowTrigger.target == code).order_by(WorkflowTrigger.id)).scalars():
        out.triggers.append({"id": tr.id, "workflow": tr.workflow_code, "kind": tr.kind, "debounce": tr.debounce_sec, "enabled": tr.enabled})
    sc = active_schema(session)
    if sc is not None:
        out.ontology = sorted(
            {c.get("ko") or c["label"] for c in sc.classes or [] if any(bk.get("dataset") in names for bk in c.get("backing") or [])}
            | {r.get("ko") or r.get("type") or "" for r in sc.relations or [] if any(bk.get("dataset") in names for bk in r.get("backing") or [])}
            - {""}
        )
    from nhdip.models import OntologyProposal

    needle = f'"{code}"'
    out.proposals = [p.id for p in session.execute(select(OntologyProposal).where(OntologyProposal.status == "pending")).scalars() if needle in json.dumps(p.ops or [], ensure_ascii=False)]
    out.contracts = sum(1 for c in session.execute(select(ColumnContract).where(ColumnContract.active)).scalars() if names & {(c.binding or {}).get("base_ym"), (c.binding or {}).get("dataset")})
    out.pending = int(session.execute(select(func.count()).select_from(UploadRequest).where(UploadRequest.kind == "dataset", UploadRequest.target == code, UploadRequest.status.in_(["pending", "draft"]))).scalar() or 0)
    wf_codes = {m["workflow"] for m in out.metrics if m["workflow"]} | {b["workflow"] for b in out.bindings if b["workflow"]} | {t["workflow"] for t in out.triggers}
    wf_codes |= {by_code[c].workflow_code for c in out.metric_codes if by_code[c].workflow_code}  # 자료 이름으로 읽는 업무 구성 흐름도 다시 돌아 '자료 대기'를 보인다
    # 영향 워크플로 = 켜져 있는 것만(멈춘 · 은퇴한 분석 에이전트의 워크플로는 다시 돌지 않는다 — 그 지표 · 트리거는 그래도 함께 정리)
    names = dict(session.execute(select(Workflow.code, Workflow.name).where(Workflow.code.in_(wf_codes or {""}), Workflow.enabled)).all())
    out.workflows = [{"code": w, "name": names[w]} for w in sorted(wf_codes) if w in names]
    return out


@dataclass
class CascadeResult:
    code: str
    removed: dict[str, Any] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    purge_ids: list[int] = field(default_factory=list)
    rerun: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"deleted": self.code, "removed": self.removed, "rerun": self.rerun, "purgeTasks": self.purge_ids}


def suppress_seed(session: Session, code: str) -> None:
    """지운 시드 정의는 다음 기동에 다시 넣지 않는다 (Q194)."""
    st = session.get(Setting, SUPPRESSED)
    sup = list(st.value) if st is not None and isinstance(st.value, list) else []
    if code not in sup:
        sup.append(code)
    if st is None:
        session.add(Setting(key=SUPPRESSED, value=sup, description="관리자가 지운 데이터셋 정의 — 시드가 다시 넣지 않는다(Phase M · Q194). 빼면 다음 기동에 시드 정의가 돌아온다"))
    else:
        st.value = sup


def drop_definition(session: Session, ds: Dataset) -> None:
    """정의 · 삭제 표시만 남은 버전 기록 · 구조 파악 결과를 지운다(행은 이미 비어 있어야 한다)."""
    from nhdip.models import DataProfile

    t = source(ds.origin)
    session.execute(t.version.__table__.delete().where(t.version.dataset_code == ds.code))
    for p in session.execute(select(DataProfile).where(DataProfile.dataset_code == ds.code)).scalars():
        session.delete(p)
    session.delete(ds)
    suppress_seed(session, ds.code)


# ═════════════════════════ 이 자료로 만든 값 지우기 (M.23 · DOB-14 · Q210) ═════════════════════════
STATEMENT_KEYS = ("asOf", "rankScore", "rankBasis", "rankCalcId", "rankRule", "rankReason", "rankReasonBy")


def _walk(obj: Any, fn) -> None:
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            fn(o)
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)


def _statement_figs(d: dict[str, Any]) -> set[str]:
    from nhdip.views.template import TOKEN

    figs = d.get("figures")
    out: set[str] = set()
    if isinstance(figs, dict):
        out |= {str(k) for k in figs}
    elif isinstance(figs, list):
        out |= {str(x.get("id") if isinstance(x, dict) else x) for x in figs}
    for v in d.values():
        if isinstance(v, str) and "[[fig:" in v:
            out |= {m.group(2) for m in TOKEN.finditer(v) if m.group(1) == "fig"}
    return out


def strip_derived(payload: Any, fig_ids: set[str], metric_codes: set[str], bind_paths: list[str]) -> int:
    """산출물 사본에서 지운 자료로 계산된 것을 비운다 — 수치(Figure) 값 · 계산 근거, 그 수치를 쓰는 서술의 기준일(=계산 전으로 숨김),
    지표 표시값으로 채운 숫자 필드, 이 자료를 읽던 바인딩의 표 · 차트. 비운 곳의 수(0 이면 바뀐 것 없음)."""
    from nhdip.views.template import FIG_DROP, binding_targets, get_parent, is_figure, strip_figure

    n = 0

    def fix(d: dict[str, Any]) -> None:
        nonlocal n
        if is_figure(d) and str(d.get("id")) in fig_ids and (d.get("value") is not None or any(k in d for k in FIG_DROP)):
            strip_figure(d)
            n += 1
        if "statement" in d and d.get("asOf") and _statement_figs(d) & fig_ids:
            for k in STATEMENT_KEYS:
                if d.get(k) is not None:
                    d[k] = None
            n += 1
        for k in [k for k in d if k.endswith("Metric") and len(k) > 6 and isinstance(d[k], str) and d[k] in metric_codes]:
            if d.get(k[:-6]) is not None:
                d[k[:-6]] = None
                n += 1

    _walk(payload, fix)
    for path in bind_paths:
        for parent, fld in binding_targets(payload, path):
            try:
                obj = get_parent(payload, parent)
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if not isinstance(obj, dict):
                continue
            cur = obj.get(fld)
            if cur in (None, "", [], {}):
                continue
            obj[fld] = "" if fld == "note" else ([] if isinstance(cur, list) else ({} if isinstance(cur, dict) else None))
            for k in ("stale", "staleReason"):
                obj.pop(k, None)
            n += 1
    return n


def clear_derived(session: Session, code: str, metric_codes: list[str], binding_ids: list[int], actor: str) -> dict[str, Any]:
    """정의 삭제 — 이 자료로 계산된 값을 지운다(같은 트랜잭션). 지표를 끄기만 하면 다음 계산이 그 수치를 건드리지 않아
    지운 자료로 낸 옛 값이 화면에 그대로 남는다(M.23 이전). 대상:
      화면 산출물  현재 세대에서 비우고 새 세대로 게시(produced_by=deletion), 그 값이 든 지난 세대는 지운다. 올린 자료가 하나도 남지 않으면
                   모든 현재 산출물을 값 없는 틀로 둔다(엔진의 '자료 없음' 처리와 같음).
      계산 기록    이 지표들의 calc.metric_value · calc.calc_run(판정 '#band' 포함) — 정의와 원천이 모두 사라져 다시 쓸 일이 없다
      실행 기록    지표 계산 노드 출력의 값 · 변화 · 오류, 화면 갱신 노드의 수치 변경 목록에서 이 지표 · 수치를 뺀다
    LLM 호출 기록(감사용 원문)은 건드리지 않는다 — 모두 비우려면 `reset-data`."""
    from sqlalchemy import delete as sql_delete

    from nhdip.graph.projection import has_uploaded_data
    from nhdip.models import CalcRun, MetricValue, NodeRun, ViewArtifact, WorkflowRun
    from nhdip.views.store import publish
    from nhdip.views.template import to_template

    codes = set(metric_codes)
    ms = list(session.execute(select(Metric).where(Metric.code.in_(codes or {""}))).scalars())
    fig_ids = {str(f) for m in ms for f in (m.figure_ids or [m.code])}
    all_binds = list(session.execute(select(ViewBinding)).scalars())
    paths: dict[str, list[str]] = {}
    for b in all_binds:
        if b.id in set(binding_ids):
            paths.setdefault(b.artifact_key, []).append(b.path)
    tpl_binds = [{"artifact_key": b.artifact_key, "path": b.path} for b in all_binds]
    empty = not has_uploaded_data(session)
    out: dict[str, Any] = {"republished": [], "cleared": 0, "generations": 0, "calcRuns": 0, "metricValues": 0, "nodeRuns": 0, "noDataLeft": empty}

    def base(key: str) -> str:
        return key.split("@", 1)[0]

    def strip(key: str, payload: Any) -> tuple[Any, int]:
        p = copy.deepcopy(payload)
        if empty:
            t = to_template(base(key), p, tpl_binds)
            return t, int(t != payload)
        return p, strip_derived(p, fig_ids, codes, paths.get(base(key), []))

    for row in session.execute(select(ViewArtifact).where(ViewArtifact.is_current).order_by(ViewArtifact.key)).scalars().all():
        p, n = strip(row.key, row.payload)
        if not n:
            continue
        publish(session, row.key, p, produced_by="deletion", changes=[{"artifact": row.key, "definitionDeleted": code, "cleared": n}])
        out["republished"].append(row.key)
        out["cleared"] += n
    session.flush()
    # 지난 세대 — 지운 값이 든 것(자료가 하나도 남지 않으면 모두)
    for row in session.execute(select(ViewArtifact).where(~ViewArtifact.is_current)).scalars().all():
        if empty or strip(row.key, row.payload)[1]:
            session.delete(row)
            out["generations"] += 1
    if codes:
        head = func.split_part(CalcRun.metric_code, "#", 1)
        out["metricValues"] = int(session.execute(sql_delete(MetricValue).where(func.split_part(MetricValue.metric_code, "#", 1).in_(codes))).rowcount or 0)
        out["calcRuns"] = int(session.execute(sql_delete(CalcRun).where(head.in_(codes))).rowcount or 0)
        wfs = {m.workflow_code for m in ms if m.workflow_code}
        run_ids = select(WorkflowRun.id).where(WorkflowRun.workflow_code.in_(wfs or {""}))
        for nr in session.execute(select(NodeRun).where(NodeRun.impl.in_(("compute_metrics", "build_views")), NodeRun.workflow_run_id.in_(run_ids))).scalars():
            o = nr.output if isinstance(nr.output, dict) else None
            if not o:
                continue
            new = dict(o)
            for k in ("values", "changed", "errors"):
                if isinstance(new.get(k), dict):
                    new[k] = {c: v for c, v in new[k].items() if c not in codes}
            if isinstance(new.get("figure_changes"), list):
                new["figure_changes"] = [c for c in new["figure_changes"] if not (isinstance(c, dict) and str(c.get("figure")) in fig_ids)]
            if new != o:
                nr.output = new
                out["nodeRuns"] += 1
    session.flush()
    if out["republished"]:
        from nhdip.knowledge.indexer import index_artifacts

        try:
            with session.begin_nested():
                index_artifacts(session, out["republished"])  # 질문하기 색인(app.kb_chunk) — Elasticsearch 는 워커 대조가 맞춘다
        except Exception as exc:  # noqa: BLE001 — 색인 실패가 삭제를 막지 않는다
            log.warning("정의 삭제 뒤 색인 갱신 실패(워커 대조가 복구): %s", exc)
            out["indexError"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    out["screens"] = len(out["republished"])
    out["republished"] = out["republished"][:50]
    return out


def unlink_ontology(session: Session, code: str, proposal_ids: list[int], actor: str) -> dict[str, Any]:
    """온톨로지에서 이 자료를 원천으로 쓰던 곳 — 객체 · 링크 유형의 원천(backing)을 뺀 새 판을 만들고(유형 자체는 남김),
    이 자료를 원천으로 추가하려던 승인 대기 제안은 '대체됨'으로 닫는다. 원천이 사라진 스키마는 편집 검증(원천 데이터셋 확인)에 걸린다."""
    from nhdip.graph.projection import active_schema
    from nhdip.graph.proposals import activate_schema
    from nhdip.models import OntologyProposal

    from nhdip.data.sources import Resolver

    out: dict[str, Any] = {"schemaVersion": None, "backing": 0, "proposals": 0}
    # 원천은 코드 · 자료 이름(업무 구성) · 정의 이름으로 가리킬 수 있다 — 이 자료를 가리키는 이름 모두
    names = Resolver(session).refs_for(code)
    sc = active_schema(session)
    if sc is not None:
        classes, relations, n = copy.deepcopy(sc.classes or []), copy.deepcopy(sc.relations or []), 0
        for item in [*classes, *relations]:
            bk = item.get("backing")
            if isinstance(bk, list) and any(isinstance(b, dict) and b.get("dataset") in names for b in bk):
                item["backing"] = [b for b in bk if not (isinstance(b, dict) and b.get("dataset") in names)]
                n += 1
        if n:
            out["schemaVersion"] = activate_schema(session, {"classes": classes, "relations": relations, "aliases": sc.aliases, "interfaces": sc.interfaces or []},
                                                   note=f"데이터셋 정의 삭제({code}) — 원천 {n}곳 제거", actor=actor)
            out["backing"] = n
    for pid in proposal_ids:
        p = session.get(OntologyProposal, pid)
        if p is not None and p.status == "pending":
            p.status, p.decided_by, p.decided_at, p.note = "superseded", actor, utcnow(), f"데이터셋 정의 삭제({code}) — 원천 자료가 없어 닫음"
            out["proposals"] += 1
    return out


def delete_with_links(session: Session, ds: Dataset, actor: str, reason: str | None, ip: str | None = None) -> CascadeResult:
    """연결까지 정의 삭제 — 호출한 쪽이 커밋하고, 커밋 뒤 res.files · res.purge_ids 를 정리한다(deletion.after_commit)."""
    from nhdip.locks import lock

    why = clean_reason(reason)
    lock(session, f"ds:{ds.origin}:{ds.code}")  # 업로드 · 버전 삭제와 같은 잠금 — 목록을 읽는 사이에 새 버전이 들어오지 않게
    lk = links(session, ds)
    if lk.pending:
        raise DeleteError(lk.as_dict()["blocked"])
    res = CascadeResult(ds.code)
    rows = 0
    # 현재 버전을 먼저 지우면 같은 기준일의 이전 버전이 현재로 올라온다 — 그 버전도 곧 지우므로 순서는 상관없지만, 기록이 읽기 쉽게 최신부터
    for v in sorted(lk.versions, key=lambda x: -x["version"]):
        r = delete_dataset_version(session, ds, v["id"], actor, why, ip, via="definition")
        rows += int(r.removed.get("rows", 0))
        res.files += r.files
        res.purge_ids += r.purge_ids
    session.flush()
    for m in lk.metrics:
        session.get(Metric, m["code"]).enabled = False
    for b in lk.bindings:
        session.get(ViewBinding, b["id"]).enabled = False
    for tr in lk.triggers:
        session.delete(session.get(WorkflowTrigger, tr["id"]))
    session.flush()
    derived = clear_derived(session, ds.code, lk.metric_codes, lk.binding_ids, actor)
    onto = unlink_ontology(session, ds.code, lk.proposals, actor)
    snapshot = {
        "name": ds.name,
        "origin": ds.origin,
        "reason": why,
        "versions": [v["version"] for v in lk.versions],
        "rows": rows,
        "metrics_disabled": [m["code"] for m in lk.metrics],
        "bindings_disabled": [{"id": b["id"], "workflow": b["workflow"], "builder": b["builder"]} for b in lk.bindings],
        "triggers_removed": [{"workflow": t["workflow"], "kind": t["kind"], "debounce": t["debounce"]} for t in lk.triggers],
        "ontology_backing": lk.ontology,
        "ontology": onto,
        "contract_columns": lk.contracts,
        "derived": {k: v for k, v in derived.items() if k != "republished"},
    }
    drop_definition(session, ds)
    emit(session, "config.changed", {"kind": "dataset", "code": ds.code, "deleted": True}, actor)
    if lk.has_current and not derived["noDataLeft"]:
        # 디스패처는 커밋 뒤 끊긴 연결(꺼진 지표 · 바인딩, 지운 트리거)을 보지 못하므로 — 이 자료로 계산하던 워크플로를 직접 한 번 다시 돌린다
        for w in lk.workflows:  # 켜진 워크플로만 들어 있다
            if w["code"] not in BASE_WORKFLOWS:
                emit(session, "manual", {"workflow": w["code"], "reason": f"데이터셋 정의 삭제({ds.code}) 뒤 다시 계산"}, actor)
                res.rerun.append(w["code"])
    res.removed = {
        "versions": len(lk.versions), "rows": rows, "metricsDisabled": len(lk.metrics), "bindingsDisabled": len(lk.bindings), "triggersRemoved": len(lk.triggers),
        "ontology": lk.ontology, "contracts": lk.contracts,
        # M.23 — 이 자료로 계산된 값 · 온톨로지 원천
        "screensCleared": derived["screens"], "generationsRemoved": derived["generations"], "calcRunsRemoved": derived["calcRuns"], "metricValuesRemoved": derived["metricValues"],
        "nodeRunsScrubbed": derived["nodeRuns"], "noDataLeft": derived["noDataLeft"], "ontologyBackingRemoved": onto["backing"], "ontologySchemaVersion": onto["schemaVersion"], "proposalsClosed": onto["proposals"],
    }
    audit(session, actor, "admin.dataset.delete_cascade", "dataset", ds.code, snapshot, ip)
    return res
