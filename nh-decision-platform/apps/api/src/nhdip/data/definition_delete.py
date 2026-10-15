"""데이터셋 정의 삭제 — 연결까지 함께 (Phase M 후속 · 요구사항 DOB-12 · Q208).

정의만 지우는 기존 삭제(DELETE /admin/datasets/{code})는 이 정의를 쓰는 곳(버전 · 지표 · 화면 바인딩 · 트리거)이 남아 있으면 막는다.
시드가 넣은 업무 화면 연결 정의는 늘 지표 · 바인딩이 읽으므로 화면에서 지울 방법이 없었다. 여기서는 확인을 받고 연결까지 함께 정리한다.

  올라온 버전   모두 삭제(버전 삭제와 같은 경로 — 행 · 원본 파일 · 그래프 · 지난 산출물 세대, 삭제 표시 기록은 정의와 함께 지움)
  지표          이 자료를 읽는 지표와 그 지표를 이어 쓰는 파생 지표를 '끔'(enabled=false) — 지우지 않는다(되살리기 = [지표]에서 켬)
  화면 바인딩   이 자료를 읽는 바인딩을 '끔'
  트리거        이 자료를 기다리는 워크플로 트리거(dataset · master)를 지움 — 다시 이으려면 [연결 도우미]
  온톨로지 원천 스키마는 바꾸지 않는다(자료가 없으면 객체가 만들어지지 않음) — [온톨로지]에서 정리하도록 알린다
  처리 중 요청  승인 대기 · 초안 요청이 있으면 막는다(먼저 반려 · 버림)
현재 버전이 있었으면 연결이 끊긴 워크플로를 한 번 다시 돌려 화면을 자료 없는 상태로 맞춘다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.events import audit, emit
from nhdip.models import Dataset, Metric, Setting, UploadRequest, ViewBinding, Workflow, WorkflowTrigger, source

from .deletion import DELETED, DeleteError, clean_reason, delete_dataset_version

SUPPRESSED = "seed.suppressed_datasets"
BASE_WORKFLOWS = {"wf_graph_projection", "wf_ontology_build"}  # 모든 자료를 읽는 기반 워크플로 — 정의 변경 이벤트로 따로 돈다


def _datasets_in(obj: Any) -> set[str]:
    from nhdip.graph.projection import _datasets_in_args

    return _datasets_in_args(obj)


def metric_closure(metrics: list[Metric], code: str) -> tuple[list[str], list[str]]:
    """(이 자료를 바로 읽는 지표, 그 지표를 {"metric": X} 로 이어 쓰는 파생 지표)."""
    direct = {m.code for m in metrics if code in _datasets_in(m.args)}
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
    bindings: list[dict[str, Any]] = field(default_factory=list)
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
    metrics = list(session.execute(select(Metric)).scalars())
    direct, derived = metric_closure(metrics, code)
    by_code = {m.code: m for m in metrics}
    for c in direct + derived:
        m = by_code[c]
        if m.enabled:
            out.metrics.append({"code": c, "label": m.label, "workflow": m.workflow_code, "derived": c in derived})
    for b in session.execute(select(ViewBinding).order_by(ViewBinding.id)).scalars():
        if b.enabled and code in _datasets_in(b.params):
            out.bindings.append({"id": b.id, "workflow": b.workflow_code, "builder": b.builder, "artifact": b.artifact_key, "path": b.path})
    for tr in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.kind.in_(["dataset", "master"]), WorkflowTrigger.target == code).order_by(WorkflowTrigger.id)).scalars():
        out.triggers.append({"id": tr.id, "workflow": tr.workflow_code, "kind": tr.kind, "debounce": tr.debounce_sec, "enabled": tr.enabled})
    sc = active_schema(session)
    if sc is not None:
        out.ontology = sorted(
            {c.get("ko") or c["label"] for c in sc.classes or [] if any(bk.get("dataset") == code for bk in c.get("backing") or [])}
            | {r.get("ko") or r.get("type") or "" for r in sc.relations or [] if any(bk.get("dataset") == code for bk in r.get("backing") or [])}
            - {""}
        )
    out.contracts = sum(1 for c in session.execute(select(ColumnContract).where(ColumnContract.active)).scalars() if code in {(c.binding or {}).get("base_ym"), (c.binding or {}).get("dataset")})
    out.pending = int(session.execute(select(func.count()).select_from(UploadRequest).where(UploadRequest.kind == "dataset", UploadRequest.target == code, UploadRequest.status.in_(["pending", "draft"]))).scalar() or 0)
    wf_codes = {m["workflow"] for m in out.metrics if m["workflow"]} | {b["workflow"] for b in out.bindings if b["workflow"]} | {t["workflow"] for t in out.triggers}
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
        "contract_columns": lk.contracts,
    }
    drop_definition(session, ds)
    emit(session, "config.changed", {"kind": "dataset", "code": ds.code, "deleted": True}, actor)
    if lk.has_current:
        # 디스패처는 커밋 뒤 끊긴 연결(꺼진 지표 · 바인딩, 지운 트리거)을 보지 못하므로 — 이 자료로 계산하던 워크플로를 직접 한 번 다시 돌린다
        for w in lk.workflows:  # 켜진 워크플로만 들어 있다
            if w["code"] not in BASE_WORKFLOWS:
                emit(session, "manual", {"workflow": w["code"], "reason": f"데이터셋 정의 삭제({ds.code}) 뒤 다시 계산"}, actor)
                res.rerun.append(w["code"])
    res.removed = {"versions": len(lk.versions), "rows": rows, "metricsDisabled": len(lk.metrics), "bindingsDisabled": len(lk.bindings), "triggersRemoved": len(lk.triggers), "ontology": lk.ontology, "contracts": lk.contracts}
    audit(session, actor, "admin.dataset.delete_cascade", "dataset", ds.code, snapshot, ip)
    return res
