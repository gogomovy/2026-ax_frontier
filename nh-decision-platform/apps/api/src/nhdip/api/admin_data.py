"""관리자 API (2/2) — 워크플로우 · 데이터셋/문서 · 지표 · 온톨로지 · 모니터링 (ADM-08~11)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.calc import catalog
from nhdip.calc.metrics import EvalContext, evaluate
from nhdip.data.datasets import IngestError, ingest_file, preview_file, rollback
from nhdip.data.documents import DocumentError, ingest_document
from nhdip.db import get_session
from nhdip.events import audit, emit
from nhdip.graph.neo4j_client import GraphUnavailable, run as graph_run
from nhdip.graph.projection import active_schema, impact_of_dataset, stats as graph_stats
from nhdip.models import (
    AppUser,
    AuditLog,
    CalcRun,
    Dataset,
    ExtractionIssue,
    Job,
    LlmCall,
    Metric,
    MetricValue,
    NodeRun,
    OntologySchema,
    OutboxEvent,
    RequestLog,
    Setting,
    ViewArtifact,
    ViewBinding,
    Workflow,
    WorkflowNode,
    WorkflowRun,
    WorkflowTrigger,
    source,
    utcnow,
)
from nhdip.views.builders import DESCRIPTIONS as BUILDER_DESC
from nhdip.workflow.dispatcher import match_event
from nhdip.workflow.engine import NODE_DESCRIPTIONS

from .deps import client_ip, require_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
MAX_UPLOAD = 200 * 1024 * 1024  # 읽기 상한(메모리 보호) — 실제 허용 크기는 설정 upload.policy.max_mb


def _iso(v):
    return v.isoformat() if v else None


def _config_changed(session: Session, kind: str, code: str, actor: str) -> None:
    emit(session, "config.changed", {"kind": kind, "code": code}, actor)


# ═════════════════════════ 워크플로우 ═════════════════════════
class WorkflowPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    outputs: list[str] | None = None


class NodeIn(BaseModel):
    key: str
    name: str
    impl: str
    seq: int
    agent_code: str | None = None
    enabled: bool = True
    config: dict[str, Any] = {}


class NodePatch(BaseModel):
    name: str | None = None
    impl: str | None = None
    seq: int | None = None
    agent_code: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class TriggerIn(BaseModel):
    kind: str
    target: str
    debounce_sec: int | None = None
    enabled: bool = True


def _next_fire(session: Session, t: WorkflowTrigger) -> str | None:
    if t.kind != "cron" or not t.enabled:
        return None
    from nhdip.workflow.scheduler import _tz, is_valid, next_fire

    if not is_valid(t.target):
        return "invalid"
    return next_fire(t.target, t.last_fired_at or utcnow(), _tz(session)).isoformat()


def _check_trigger(kind: str, target: str) -> None:
    from nhdip.workflow.scheduler import is_valid

    if kind not in ("dataset", "master", "doc_class", "rule", "setting", "event", "any", "cron"):
        raise HTTPException(422, f"알 수 없는 트리거 종류: {kind}")
    if kind == "cron" and not is_valid(target):
        raise HTTPException(422, "cron 식 오류 — '분 시 일 월 요일' (예: 0 6 * * 1-5 → 평일 06:00)")


def _wf_json(session: Session, w: Workflow) -> dict[str, Any]:
    import nhdip.workflow.nodes  # noqa: F401

    nodes = session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == w.code).order_by(WorkflowNode.seq)).scalars().all()
    trig = session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == w.code).order_by(WorkflowTrigger.id)).scalars().all()
    runs = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == w.code).order_by(WorkflowRun.started_at.desc()).limit(5)).scalars().all()
    queued = session.execute(select(Job).where(Job.workflow_code == w.code, Job.status.in_(["queued", "running"]))).scalars().all()
    n_metrics = session.execute(select(func.count()).select_from(Metric).where(Metric.workflow_code == w.code, Metric.enabled)).scalar()
    return {
        "code": w.code,
        "name": w.name,
        "description": w.description,
        "enabled": w.enabled,
        "outputs": w.outputs,
        "metrics": n_metrics,
        "nodes": [{"id": n.id, "seq": n.seq, "key": n.key, "name": n.name, "impl": n.impl, "implDescription": NODE_DESCRIPTIONS.get(n.impl), "agentCode": n.agent_code, "enabled": n.enabled, "config": n.config} for n in nodes],
        "triggers": [{"id": t.id, "kind": t.kind, "target": t.target, "debounceSec": t.debounce_sec, "enabled": t.enabled, "lastFiredAt": _iso(t.last_fired_at), "nextFireAt": _next_fire(session, t)} for t in trig],
        "recentRuns": [{"id": r.id, "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at), "causes": len(r.causes or [])} for r in runs],
        "pendingJobs": [{"id": j.id, "status": j.status, "runAfter": _iso(j.run_after), "causes": len(j.causes or [])} for j in queued],
    }


@router.get("/workflows")
def workflows(session: Session = Depends(get_session)):
    import nhdip.workflow.nodes  # noqa: F401

    return {
        "workflows": [_wf_json(session, w) for w in session.execute(select(Workflow).order_by(Workflow.sort)).scalars()],
        "impls": [{"key": k, "description": v} for k, v in NODE_DESCRIPTIONS.items()],
        "triggerKinds": ["dataset", "master", "doc_class", "rule", "setting", "event", "any", "cron"],
    }


def _wf(session: Session, code: str) -> Workflow:
    w = session.get(Workflow, code)
    if not w:
        raise HTTPException(404, "워크플로우 없음")
    return w


@router.patch("/workflows/{code}")
def wf_patch(code: str, body: WorkflowPatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    patch = body.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(w, k, v)
    _config_changed(session, "workflow", code, admin.emp_no)
    audit(session, admin.emp_no, "admin.workflow.update", "workflow", code, patch, client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.post("/workflows/{code}/nodes", status_code=201)
def node_create(code: str, body: NodeIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    session.add(WorkflowNode(workflow_code=code, **body.model_dump()))
    audit(session, admin.emp_no, "admin.workflow.node_create", "workflow", code, body.model_dump(), client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.patch("/workflows/{code}/nodes/{nid}")
def node_patch(code: str, nid: int, body: NodePatch, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    n = session.get(WorkflowNode, nid)
    if not n or n.workflow_code != code:
        raise HTTPException(404, "노드 없음")
    patch = body.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(n, k, v)
    audit(session, admin.emp_no, "admin.workflow.node_update", "workflow", code, {"node": n.key, **patch}, client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.delete("/workflows/{code}/nodes/{nid}")
def node_delete(code: str, nid: int, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    n = session.get(WorkflowNode, nid)
    if not n or n.workflow_code != code:
        raise HTTPException(404, "노드 없음")
    session.delete(n)
    audit(session, admin.emp_no, "admin.workflow.node_delete", "workflow", code, {"node": n.key}, client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.post("/workflows/{code}/triggers", status_code=201)
def trigger_create(code: str, body: TriggerIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    _check_trigger(body.kind, body.target)
    session.add(WorkflowTrigger(workflow_code=code, **body.model_dump()))
    _config_changed(session, "trigger", code, admin.emp_no)
    audit(session, admin.emp_no, "admin.workflow.trigger_create", "workflow", code, body.model_dump(), client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.patch("/workflows/{code}/triggers/{tid}")
def trigger_patch(code: str, tid: int, body: dict[str, Any], request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    t = session.get(WorkflowTrigger, tid)
    if not t or t.workflow_code != code:
        raise HTTPException(404, "트리거 없음")
    _check_trigger(body.get("kind", t.kind), body.get("target", t.target))
    for k in ("kind", "target", "debounce_sec", "enabled"):
        if k in body:
            setattr(t, k, body[k])
    if "target" in body and t.kind == "cron":
        t.last_fired_at = None  # 식이 바뀌면 다음 예정 시각부터 다시 계산
    _config_changed(session, "trigger", code, admin.emp_no)
    audit(session, admin.emp_no, "admin.workflow.trigger_update", "workflow", code, body, client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.delete("/workflows/{code}/triggers/{tid}")
def trigger_delete(code: str, tid: int, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    w = _wf(session, code)
    t = session.get(WorkflowTrigger, tid)
    if not t or t.workflow_code != code:
        raise HTTPException(404, "트리거 없음")
    session.delete(t)
    _config_changed(session, "trigger", code, admin.emp_no)
    audit(session, admin.emp_no, "admin.workflow.trigger_delete", "workflow", code, {"trigger": tid}, client_ip(request))
    session.commit()
    return _wf_json(session, w)


@router.post("/workflows/{code}/run")
def wf_run(code: str, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    _wf(session, code)
    ev = emit(session, "manual", {"workflow": code, "reason": "관리자 수동 실행"}, admin.emp_no)
    audit(session, admin.emp_no, "admin.workflow.run", "workflow", code, None, client_ip(request))
    session.commit()
    return {"queued": True, "event": ev.id}


@router.get("/impact")
def impact(event_type: str = "dataset.committed", dataset: str | None = None, doc_class: str | None = None, rule: str | None = None, session: Session = Depends(get_session)):
    """이 변경이 일어나면 어떤 워크플로우가 도는가 — 실제 디스패처 매칭 로직으로 미리보기 + 그래프 계보."""
    payload = {k: v for k, v in {"dataset": dataset, "doc_class": doc_class, "rule": rule}.items() if v}
    ev = OutboxEvent(id=0, type=event_type, payload=payload)
    out: dict[str, Any] = {"matched": match_event(session, ev)}
    if dataset:
        try:
            out["graph"] = impact_of_dataset(dataset)
        except GraphUnavailable as exc:
            out["graph_error"] = str(exc)[:200]
    return out


# ═════════════════════════ 데이터셋 ═════════════════════════
class DatasetIn(BaseModel):
    code: str
    name: str
    origin: str
    kind: str = "fact"
    description: str = ""
    file_pattern: str | None = None
    refresh_cycle: str | None = None
    columns: list[dict[str, Any]] = []
    key_columns: list[str] = []
    as_of_column: str | None = None
    mapping: dict[str, Any] = {}
    quality_rules: list[dict[str, Any]] = []
    parser: dict[str, Any] = {}
    active: bool = True


def _ds(session: Session, code: str) -> Dataset:
    d = session.get(Dataset, code)
    if not d:
        raise HTTPException(404, "데이터셋 없음")
    return d


def _ds_json(session: Session, d: Dataset, with_versions: bool = True) -> dict[str, Any]:
    t = source(d.origin)
    out: dict[str, Any] = {k: getattr(d, k) for k in ("code", "name", "origin", "kind", "description", "file_pattern", "refresh_cycle", "columns", "key_columns", "as_of_column", "mapping", "quality_rules", "parser", "materialize", "active")}
    out["storage"] = f"{d.origin}.row_store"
    metrics = [m.code for m in session.execute(select(Metric)).scalars() if d.code in str(m.args)]
    out["usedByMetrics"] = metrics
    if with_versions:
        vs = session.execute(select(t.version).where(t.version.dataset_code == d.code).order_by(t.version.version.desc()).limit(30)).scalars().all()
        # 최근 30개 밖으로 밀린 현재 버전도 항상 포함 (되돌리기 · 정정이 쌓여도 기준일별 현재 버전이 보이도록)
        have = {v.id for v in vs}
        vs = [*vs, *[v for v in session.execute(select(t.version).where(t.version.dataset_code == d.code, t.version.is_current)).scalars() if v.id not in have]]
        out["versions"] = [{"id": v.id, "version": v.version, "asOf": _iso(v.as_of), "status": v.status, "isCurrent": v.is_current, "dataOrigin": v.data_origin, "fileName": v.file_name, "sha256": v.file_sha256, "rows": v.row_count, "quality": v.quality, "uploadedBy": v.uploaded_by, "createdAt": _iso(v.created_at), "committedAt": _iso(v.committed_at), "note": v.note} for v in vs]
    return out


@router.get("/datasets")
def datasets(session: Session = Depends(get_session)):
    return [_ds_json(session, d) for d in session.execute(select(Dataset).order_by(Dataset.origin, Dataset.code)).scalars()]


@router.post("/datasets", status_code=201)
def dataset_create(body: DatasetIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if body.origin not in ("bank", "ext"):
        raise HTTPException(422, "origin 은 bank(당행) | ext(외부)")
    if session.get(Dataset, body.code):
        raise HTTPException(409, "이미 있는 데이터셋 코드")
    d = Dataset(**body.model_dump())
    session.add(d)
    _config_changed(session, "dataset", body.code, admin.emp_no)
    audit(session, admin.emp_no, "admin.dataset.create", "dataset", body.code, {"origin": body.origin}, client_ip(request))
    session.commit()
    return _ds_json(session, d)


@router.patch("/datasets/{code}")
def dataset_patch(code: str, body: dict[str, Any], request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    d = _ds(session, code)
    allowed = set(DatasetIn.model_fields) - {"code", "origin"}
    patch = {k: v for k, v in body.items() if k in allowed}
    for k, v in patch.items():
        setattr(d, k, v)
    _config_changed(session, "dataset", code, admin.emp_no)
    audit(session, admin.emp_no, "admin.dataset.update", "dataset", code, patch, client_ip(request))
    session.commit()
    return _ds_json(session, d)


async def _read(file: UploadFile, purpose: str, session: Session, request: Request | None = None, actor: str | None = None) -> tuple[str, bytes]:
    """업로드 읽기 + 보안 검사(8.4.4) — 정책은 설정 `upload.policy`. 차단은 감사 `upload.rejected` 로 남긴다."""
    from nhdip.data.filecheck import UploadRejected, check_upload

    content = await file.read(MAX_UPLOAD + 1)
    pol = session.get(Setting, "upload.policy")
    try:
        if len(content) > MAX_UPLOAD:
            raise UploadRejected("파일이 너무 큽니다")
        name = check_upload(file.filename, content, purpose, pol.value if pol else None)
    except UploadRejected as exc:
        session.rollback()
        audit(session, actor, "upload.rejected", purpose, (file.filename or "")[:120], {"reason": str(exc), "bytes": len(content)}, client_ip(request) if request else None)
        session.commit()
        raise HTTPException(413 if "너무 큽니다" in str(exc) else 422, str(exc)) from exc
    return name, content


@router.post("/datasets/{code}/preview")
async def dataset_preview(code: str, request: Request, file: UploadFile = File(...), session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    d = _ds(session, code)
    name, content = await _read(file, "dataset", session, request, admin.emp_no)
    try:
        return preview_file(d, name, content)
    except (IngestError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/datasets/{code}/upload", status_code=201)
async def dataset_upload(
    code: str,
    request: Request,
    file: UploadFile = File(...),
    origin: str = Form(...),
    data_origin: str = Form("actual"),
    as_of: str | None = Form(None),
    note: str | None = Form(None),
    force: bool = Form(False),
    session: Session = Depends(get_session),
    admin: AppUser = Depends(require_admin),
):
    d = _ds(session, code)
    if origin != d.origin:
        # 당행/외부 구분을 업로드 단계에서 한 번 더 확인 (ING-01)
        raise HTTPException(422, f"이 데이터셋은 {'당행' if d.origin == 'bank' else '외부'} 데이터입니다. 출처 구분을 확인하세요.")
    if data_origin not in ("actual", "simulated"):
        raise HTTPException(422, "data_origin 은 actual | simulated")
    name, content = await _read(file, "dataset", session, request, admin.emp_no)
    try:
        v = ingest_file(session, d, name, content, as_of=as_of or None, data_origin=data_origin, actor=admin.emp_no, note=note, force=force)
    except (IngestError, ValueError) as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"version": v.version, "id": v.id, "status": v.status, "quality": v.quality, "rows": v.row_count, "isCurrent": v.is_current}


@router.post("/datasets/{code}/versions/{vid}/rollback")
def dataset_rollback(code: str, vid: int, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    d = _ds(session, code)
    try:
        v = rollback(session, d, vid, admin.emp_no)
    except IngestError as exc:
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"ok": True, "version": v.version}


@router.get("/datasets/{code}/versions/{vid}/rows")
def dataset_rows(code: str, vid: int, limit: int = 200, session: Session = Depends(get_session)):
    d = _ds(session, code)
    t = source(d.origin)
    rows = session.execute(select(t.row).where(t.row.version_id == vid).order_by(t.row.row_no).limit(min(limit, 2000))).scalars().all()
    return {"columns": [c["name"] for c in d.columns], "rows": [r.data for r in rows]}


# ═════════════════════════ 문서 ═════════════════════════
@router.get("/documents")
def admin_documents(session: Session = Depends(get_session)):
    out = []
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in session.execute(select(t.document).order_by(t.document.created_at.desc())).scalars():
            chunks = session.execute(select(func.count(), func.count(t.chunk.embedding)).where(t.chunk.document_id == d.id)).one()
            issues = session.execute(select(func.count()).select_from(ExtractionIssue).where(ExtractionIssue.origin == origin, ExtractionIssue.document_id == d.id, ExtractionIssue.status == "open")).scalar()
            ex = d.extraction or {}
            out.append({"origin": origin, "id": d.id, "docCode": d.doc_code, "version": d.version, "isCurrent": d.is_current, "title": d.title, "docClass": d.doc_class, "issuer": d.issuer, "publishedAt": _iso(d.published_at), "fileName": d.file_name, "status": d.status, "chunks": chunks[0], "embedded": chunks[1], "extraction": {"by": ex.get("by"), "entities": len(ex.get("entities") or []), "relations": len(ex.get("relations") or []), "issues": ex.get("issues"), "fallbackReason": ex.get("fallback_reason")}, "openIssues": issues, "uploadedBy": d.uploaded_by, "createdAt": _iso(d.created_at)})
    return out


@router.post("/documents/upload", status_code=201)
async def document_upload(
    request: Request,
    origin: str = Form(...),
    doc_class: str = Form(...),
    title: str = Form(...),
    doc_code: str | None = Form(None),
    issuer: str | None = Form(None),
    published_at: str | None = Form(None),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    session: Session = Depends(get_session),
    admin: AppUser = Depends(require_admin),
):
    if origin not in ("bank", "ext"):
        raise HTTPException(422, "origin 은 bank(당행) | ext(외부)")
    import re

    code = doc_code or "doc-" + re.sub(r"[^0-9A-Za-z가-힣]+", "-", title)[:60].strip("-").lower()
    name, content = await _read(file, "document", session, request, admin.emp_no) if file else (None, None)
    try:
        doc = ingest_document(session, origin=origin, doc_code=code, title=title, doc_class=doc_class, text=text, filename=name, content=content, issuer=issuer, published_at=published_at or None, meta={"docType": "업로드 문서", "isOfficial": origin == "ext"}, actor=admin.emp_no)
    except (DocumentError, ValueError) as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"origin": origin, "id": doc.id, "docCode": doc.doc_code, "version": doc.version}


@router.post("/documents/{origin}/{did}/reextract")
def document_reextract(origin: str, did: int, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    t = source(origin)
    d = session.get(t.document, did)
    if not d:
        raise HTTPException(404, "문서 없음")
    d.status = "ingested"
    emit(session, "document.ingested", {"origin": origin, "document_id": d.id, "doc_code": d.doc_code, "doc_class": d.doc_class, "reextract": True}, admin.emp_no)
    audit(session, admin.emp_no, "admin.document.reextract", "document", f"{origin}:{did}", None, client_ip(request))
    session.commit()
    return {"queued": True}


@router.get("/documents/{origin}/{did}")
def document_detail(origin: str, did: int, session: Session = Depends(get_session)):
    t = source(origin)
    d = session.get(t.document, did)
    if not d:
        raise HTTPException(404, "문서 없음")
    chunks = session.execute(select(t.chunk).where(t.chunk.document_id == did).order_by(t.chunk.seq)).scalars().all()
    issues = session.execute(select(ExtractionIssue).where(ExtractionIssue.origin == origin, ExtractionIssue.document_id == did).order_by(ExtractionIssue.id.desc())).scalars().all()
    return {
        "title": d.title,
        "docClass": d.doc_class,
        "text": d.text[:20000],
        "extraction": d.extraction,
        "chunks": [{"id": c.id, "seq": c.seq, "page": c.page, "text": c.text, "embedded": c.embedding is not None, "model": c.embedding_model} for c in chunks],
        "issues": [{"id": i.id, "kind": i.kind, "reason": i.reason, "status": i.status, "raw": i.raw} for i in issues],
    }


# ═════════════════════════ 지표 · 바인딩 ═════════════════════════
class MetricIn(BaseModel):
    code: str
    label: str
    formula: str
    args: dict[str, Any]
    workflow_code: str
    unit: str = ""
    decimals: int | None = None
    rounding: str | None = None
    scale: float | None = None
    figure_ids: list[str] = []
    description: str = ""
    enabled: bool = True
    sort: int = 0


@router.get("/metrics")
def metrics(session: Session = Depends(get_session)):
    ms = session.execute(select(Metric).order_by(Metric.workflow_code, Metric.sort, Metric.code)).scalars().all()
    latest: dict[str, Any] = {}
    for mv in session.execute(select(MetricValue).order_by(MetricValue.created_at.desc()).limit(3000)).scalars():
        latest.setdefault(mv.metric_code, mv)
    return {
        "metrics": [{**{k: getattr(m, k) for k in MetricIn.model_fields}, "latest": {"display": float(latest[m.code].display_value) if m.code in latest and latest[m.code].display_value is not None else None, "previous": float(latest[m.code].previous_value) if m.code in latest and latest[m.code].previous_value is not None else None, "calcRunId": latest[m.code].calc_run_id if m.code in latest else None, "at": _iso(latest[m.code].created_at) if m.code in latest else None}} for m in ms],
        "formulas": catalog(),
        "builders": [{"key": k, "description": v} for k, v in BUILDER_DESC.items()],
        "bindings": [{"id": b.id, "workflowCode": b.workflow_code, "artifactKey": b.artifact_key, "path": b.path, "builder": b.builder, "params": b.params, "enabled": b.enabled} for b in session.execute(select(ViewBinding).order_by(ViewBinding.id)).scalars()],
    }


@router.post("/metrics", status_code=201)
def metric_create(body: MetricIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if session.get(Metric, body.code):
        raise HTTPException(409, "이미 있는 지표 코드")
    session.add(Metric(**body.model_dump()))
    _config_changed(session, "metric", body.code, admin.emp_no)
    audit(session, admin.emp_no, "admin.metric.create", "metric", body.code, body.model_dump(), client_ip(request))
    session.commit()
    return {"ok": True}


@router.patch("/metrics/{code}")
def metric_patch(code: str, body: dict[str, Any], request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    m = session.get(Metric, code)
    if not m:
        raise HTTPException(404, "지표 없음")
    allowed = set(MetricIn.model_fields) - {"code"}
    patch = {k: v for k, v in body.items() if k in allowed}
    for k, v in patch.items():
        setattr(m, k, v)
    _config_changed(session, "metric", code, admin.emp_no)
    audit(session, admin.emp_no, "admin.metric.update", "metric", code, patch, client_ip(request))
    session.commit()
    return {"ok": True}


@router.post("/metrics/{code}/preview")
def metric_preview(code: str, session: Session = Depends(get_session)):
    """현재 데이터로 계산만 해 보고 기록하지 않는다(트랜잭션 롤백)."""
    m = session.get(Metric, code)
    if not m:
        raise HTTPException(404, "지표 없음")
    ctx = EvalContext(session=session)
    deps = session.execute(select(Metric).where(Metric.workflow_code == m.workflow_code)).scalars().all()
    out = evaluate(ctx, deps)
    res = out[code]
    data = {**res.as_json(), "trace": res.trace, "inputs": ctx.used_versions}
    session.rollback()
    return data


@router.patch("/bindings/{bid}")
def binding_patch(bid: int, body: dict[str, Any], request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    b = session.get(ViewBinding, bid)
    if not b:
        raise HTTPException(404, "바인딩 없음")
    for k in ("artifact_key", "path", "builder", "params", "enabled"):
        if k in body:
            setattr(b, k, body[k])
    audit(session, admin.emp_no, "admin.binding.update", "binding", str(bid), body, client_ip(request))
    session.commit()
    return {"ok": True}


# ═════════════════════════ 온톨로지 ═════════════════════════
class SchemaIn(BaseModel):
    classes: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    aliases: dict[str, Any] = {}
    note: str | None = None


class IssuePatch(BaseModel):
    status: str


@router.get("/ontology")
def ontology(session: Session = Depends(get_session)):
    sc = active_schema(session)
    versions = session.execute(select(OntologySchema.version, OntologySchema.active, OntologySchema.note, OntologySchema.created_at).order_by(OntologySchema.version.desc())).all()
    issues = dict(session.execute(select(ExtractionIssue.kind, func.count()).where(ExtractionIssue.status == "open").group_by(ExtractionIssue.kind)).all())
    try:
        gs: dict[str, Any] = {"ok": True, **graph_stats()}
    except GraphUnavailable as exc:
        gs = {"ok": False, "error": str(exc)[:200]}
    return {
        "schema": {"version": sc.version, "classes": sc.classes, "relations": sc.relations, "aliases": sc.aliases, "note": sc.note} if sc else None,
        "versions": [{"version": v, "active": a, "note": n, "createdAt": _iso(c)} for v, a, n, c in versions],
        "graph": gs,
        "openIssues": issues,
    }


@router.put("/ontology/schema")
def ontology_put(body: SchemaIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    import re

    for c in body.classes:
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,60}$", c.get("label", "")):
            raise HTTPException(422, f"클래스 라벨 형식 오류: {c.get('label')}")
    for r in body.relations:
        if not re.match(r"^[A-Z][A-Z0-9_]{0,60}$", r.get("type", "")):
            raise HTTPException(422, f"관계 이름 형식 오류(대문자): {r.get('type')}")
    last = session.execute(select(func.max(OntologySchema.version))).scalar() or 0
    for s in session.execute(select(OntologySchema).where(OntologySchema.active)).scalars():
        s.active = False
    session.add(OntologySchema(version=last + 1, classes=body.classes, relations=body.relations, aliases=body.aliases, note=body.note, active=True))
    emit(session, "ontology.changed", {"version": last + 1}, admin.emp_no)
    audit(session, admin.emp_no, "admin.ontology.schema", "ontology", str(last + 1), {"classes": len(body.classes), "relations": len(body.relations)}, client_ip(request))
    session.commit()
    return ontology(session)


@router.get("/ontology/issues")
def ontology_issues(status: str = "open", limit: int = 200, session: Session = Depends(get_session)):
    rows = session.execute(select(ExtractionIssue).where(ExtractionIssue.status == status).order_by(ExtractionIssue.id.desc()).limit(min(limit, 1000))).scalars().all()
    return [{"id": i.id, "origin": i.origin, "documentId": i.document_id, "chunkId": i.chunk_id, "kind": i.kind, "reason": i.reason, "raw": i.raw, "status": i.status, "createdAt": _iso(i.created_at)} for i in rows]


@router.patch("/ontology/issues/{iid}")
def ontology_issue_patch(iid: int, body: IssuePatch, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    i = session.get(ExtractionIssue, iid)
    if not i:
        raise HTTPException(404, "검토 항목 없음")
    if body.status not in ("open", "accepted", "rejected"):
        raise HTTPException(422, "status 는 open | accepted | rejected")
    i.status, i.resolved_by, i.resolved_at = body.status, admin.emp_no, utcnow()
    audit(session, admin.emp_no, "admin.ontology.issue", "extraction_issue", str(iid), {"status": body.status}, None)
    session.commit()
    return {"ok": True}


@router.post("/ontology/reproject")
def ontology_reproject(request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    emit(session, "manual", {"workflow": "wf_graph_projection", "reason": "관리자 재투영"}, admin.emp_no)
    audit(session, admin.emp_no, "admin.ontology.reproject", "graph", None, None, client_ip(request))
    session.commit()
    return {"queued": True}


@router.get("/ontology/graph")
def ontology_graph(label: str | None = None, limit: int = 150):
    """시각화용 샘플 (노드·관계). label 은 스키마 형식 검증 후 사용."""
    from nhdip.graph.neo4j_client import safe_name

    try:
        where = f"WHERE a:{safe_name(label)} OR b:{safe_name(label)}" if label else ""
        rows = graph_run(f"MATCH (a)-[r]->(b) {where} RETURN a.key AS a, labels(a)[0] AS al, coalesce(a.name, a.key) AS an, type(r) AS t, b.key AS b, labels(b)[0] AS bl, coalesce(b.name, b.key) AS bn, r.extracted_by AS by LIMIT $lim", lim=min(limit, 500))
    except GraphUnavailable as exc:
        raise HTTPException(503, f"그래프 장애: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    nodes: dict[str, dict[str, Any]] = {}
    edges = []
    for r in rows:
        nodes.setdefault(f"{r['al']}:{r['a']}", {"id": f"{r['al']}:{r['a']}", "label": r["al"], "name": r["an"]})
        nodes.setdefault(f"{r['bl']}:{r['b']}", {"id": f"{r['bl']}:{r['b']}", "label": r["bl"], "name": r["bn"]})
        edges.append({"from": f"{r['al']}:{r['a']}", "to": f"{r['bl']}:{r['b']}", "type": r["t"], "by": r["by"]})
    return {"nodes": list(nodes.values()), "edges": edges}


@router.get("/ontology/map")
def ontology_map_view(limit: int = 1500, classes: str | None = None, refresh: bool = False, session: Session = Depends(get_session)):
    """온톨로지 구성 지도 (Phase G · OV-01~06) — PostgreSQL 원장에서 투영과 같은 규칙으로 모은 개체 · 관계, 군집 · 3D/2D 배치 · 구조 요약.
    Neo4j 가 없어도 동작한다(Neo4j 반영 상태는 neo4j 에 보조로)."""
    import re

    from nhdip.graph.neo4j_client import health as graph_health
    from nhdip.graph.ontology_map import MAX_LIMIT, ontology_map

    want = [c for c in (classes or "").split(",") if c]
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,60}", c) for c in want):
        raise HTTPException(422, "classes 는 클래스 이름(영문 · 숫자 · _) 쉼표 목록입니다")
    if not 10 <= limit <= MAX_LIMIT:
        raise HTTPException(422, f"limit 은 10~{MAX_LIMIT} 입니다")
    try:
        out = ontology_map(session, limit=limit, classes=want or None, refresh=refresh)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    gh = graph_health()
    return {**out, "neo4j": {"ok": bool(gh.get("ok")), **({"nodes": gh.get("nodes"), "relationships": gh.get("relationships")} if gh.get("ok") else {"error": str(gh.get("error", ""))[:160]})}}


# ═════════════════════════ 모니터링 ═════════════════════════
@router.get("/monitor/flow")
def monitor_flow(limit: int = 60, session: Session = Depends(get_session)):
    """데이터 흐름 타임라인: 변경 이벤트 → 매칭 워크플로우 → 작업 → 실행 → 게시 산출물."""
    events = session.execute(select(OutboxEvent).order_by(OutboxEvent.id.desc()).limit(min(limit, 300))).scalars().all()
    runs = session.execute(select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(200)).scalars().all()
    by_event: dict[int, list[dict[str, Any]]] = {}
    for r in runs:
        for c in r.causes or []:
            if c.get("event_id"):
                by_event.setdefault(c["event_id"], []).append({"run": r.id, "workflow": r.workflow_code, "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at), "published": (r.summary or {}).get("published", [])})
    jobs = session.execute(select(Job).where(Job.status.in_(["queued", "running", "approval"]))).scalars().all()
    pending: dict[int, list[dict[str, Any]]] = {}
    for j in jobs:
        for c in j.causes or []:
            if c.get("event_id"):
                pending.setdefault(c["event_id"], []).append({"job": j.id, "workflow": j.workflow_code, "status": j.status, "runAfter": _iso(j.run_after)})
    return [
        {"id": e.id, "type": e.type, "payload": e.payload, "actor": e.actor, "at": _iso(e.created_at), "dispatchedAt": _iso(e.dispatched_at), "matched": e.matched, "runs": by_event.get(e.id, []), "pending": pending.get(e.id, []), "traceId": e.trace_id}
        for e in events
    ]


@router.get("/jobs/approval")
def jobs_approval(session: Session = Depends(get_session)):
    """사람 승인 대기 작업 (B.32 · orchestrator.policy.require_approval)."""
    rows = session.execute(select(Job).where(Job.status == "approval").order_by(Job.created_at)).scalars().all()
    return [{"id": j.id, "workflow": j.workflow_code, "createdAt": _iso(j.created_at), "causes": [{k: c.get(k) for k in ("event_id", "type", "reasons", "actor", "at")} for c in (j.causes or [])][-20:], "causeCount": len(j.causes or [])} for j in rows]


class ApprovalIn(BaseModel):
    reason: str | None = None


@router.post("/jobs/{jid}/approve")
def job_approve(jid: int, body: ApprovalIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    # 행 잠금 — 디스패처가 같은 작업에 원인을 덧붙이는 중이면 끝날 때까지 기다린다 (B.33)
    j = session.execute(select(Job).where(Job.id == jid).with_for_update()).scalar()
    if not j or j.status != "approval":
        raise HTTPException(404, "승인 대기 작업 없음")
    from nhdip.models import utcnow as _now

    # 같은 워크플로우의 대기 작업이 있으면 원인을 합친다 (동시 실행 1개 원칙)
    q = session.execute(select(Job).where(Job.kind == "workflow", Job.workflow_code == j.workflow_code, Job.status == "queued").limit(1).with_for_update()).scalar()
    if q is not None:
        q.causes = [*q.causes, *j.causes][-200:]
        q.run_after = _now()
        j.status, j.finished_at, j.error = "done", _now(), f"승인 — 대기 작업 #{q.id} 에 병합"
    else:
        j.status, j.run_after = "queued", _now()
    audit(session, admin.emp_no, "admin.job.approve", "job", str(jid), {"workflow": j.workflow_code, "reason": body.reason}, client_ip(request))
    session.commit()
    return {"ok": True}


@router.post("/jobs/{jid}/reject")
def job_reject(jid: int, body: ApprovalIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    j = session.execute(select(Job).where(Job.id == jid).with_for_update()).scalar()
    if not j or j.status != "approval":
        raise HTTPException(404, "승인 대기 작업 없음")
    from nhdip.models import utcnow as _now

    j.status, j.finished_at, j.error = "rejected", _now(), f"반려 — {body.reason or '사유 없음'}"[:500]
    audit(session, admin.emp_no, "admin.job.reject", "job", str(jid), {"workflow": j.workflow_code, "reason": body.reason}, client_ip(request))
    session.commit()
    return {"ok": True}


@router.get("/monitor/runs")
def monitor_runs(workflow: str | None = None, limit: int = 50, session: Session = Depends(get_session)):
    q = select(WorkflowRun).order_by(WorkflowRun.started_at.desc()).limit(min(limit, 300))
    if workflow:
        q = q.where(WorkflowRun.workflow_code == workflow)
    out = []
    for r in session.execute(q).scalars():
        calls = session.execute(select(func.count(), func.sum(LlmCall.prompt_tokens), func.sum(LlmCall.completion_tokens)).where(LlmCall.workflow_run_id == r.id)).one()
        calcs = session.execute(select(func.count()).select_from(CalcRun).where(CalcRun.workflow_run_id == r.id)).scalar()
        out.append({"id": r.id, "workflow": r.workflow_code, "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at), "causes": r.causes, "summary": r.summary, "error": r.error, "llmCalls": calls[0], "tokens": (calls[1] or 0) + (calls[2] or 0), "calcRuns": calcs, "traceId": r.trace_id})
    return out


@router.get("/monitor/runs/{rid}")
def monitor_run(rid: str, session: Session = Depends(get_session)):
    r = session.get(WorkflowRun, rid)
    if not r:
        raise HTTPException(404, "실행 없음")
    nodes = session.execute(select(NodeRun).where(NodeRun.workflow_run_id == rid).order_by(NodeRun.seq)).scalars().all()
    calls = session.execute(select(LlmCall).where(LlmCall.workflow_run_id == rid).order_by(LlmCall.created_at)).scalars().all()
    calcs = session.execute(select(CalcRun).where(CalcRun.workflow_run_id == rid).order_by(CalcRun.created_at)).scalars().all()
    return {
        "run": {"id": r.id, "workflow": r.workflow_code, "status": r.status, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at), "causes": r.causes, "summary": r.summary, "error": r.error, "traceId": r.trace_id},
        "nodes": [{"id": n.id, "seq": n.seq, "key": n.node_key, "impl": n.impl, "agent": n.agent_code, "status": n.status, "input": n.input, "output": n.output, "error": n.error, "durationMs": n.duration_ms, "startedAt": _iso(n.started_at)} for n in nodes],
        "llmCalls": [_call_json(c, full=False) for c in calls],
        "calcRuns": [_calc_json(c) for c in calcs],
    }


def _call_json(c: LlmCall, full: bool = True) -> dict[str, Any]:
    d = {"id": c.id, "nodeRunId": c.node_run_id, "agent": c.agent_code, "purpose": c.purpose, "connection": c.connection_name, "model": c.model, "params": c.params, "status": c.status, "error": c.error, "promptTokens": c.prompt_tokens, "completionTokens": c.completion_tokens, "latencyMs": c.latency_ms, "createdAt": _iso(c.created_at), "output": c.output_text}
    if full:
        d["messages"] = c.messages
        d["response"] = c.response
    return d


def _calc_json(c: CalcRun) -> dict[str, Any]:
    return {"id": c.id, "formula": c.formula_id, "version": c.formula_version, "metric": c.metric_code, "inputs": c.inputs, "sources": c.sources, "result": c.result, "value": str(c.value) if c.value is not None else None, "display": float(c.display_value) if c.display_value is not None else None, "decimals": c.decimals, "rounding": c.rounding, "library": c.library, "error": c.error, "runId": c.workflow_run_id, "createdAt": _iso(c.created_at)}


@router.get("/monitor/llm-calls")
def monitor_llm_calls(agent: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    q = select(LlmCall).order_by(LlmCall.created_at.desc()).limit(min(limit, 500))
    if agent:
        q = q.where(LlmCall.agent_code == agent)
    return [_call_json(c, full=False) for c in session.execute(q).scalars()]


@router.get("/monitor/llm-calls/{cid}")
def monitor_llm_call(cid: str, session: Session = Depends(get_session)):
    c = session.get(LlmCall, cid)
    if not c:
        raise HTTPException(404, "호출 없음")
    return _call_json(c)


@router.get("/monitor/calc")
def monitor_calc(metric: str | None = None, formula: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    q = select(CalcRun).order_by(CalcRun.created_at.desc()).limit(min(limit, 1000))
    if metric:
        q = q.where(CalcRun.metric_code == metric)
    if formula:
        q = q.where(CalcRun.formula_id == formula)
    return [_calc_json(c) for c in session.execute(q).scalars()]


@router.get("/monitor/metrics")
def monitor_metrics(session: Session = Depends(get_session)):
    """지표별 최근 값 · 이전 값 · 추이(최근 20회)."""
    hist: dict[str, list[MetricValue]] = {}
    for mv in session.execute(select(MetricValue).order_by(MetricValue.created_at.desc()).limit(5000)).scalars():
        lst = hist.setdefault(mv.metric_code, [])
        if len(lst) < 20:
            lst.append(mv)
    ms = {m.code: m for m in session.execute(select(Metric)).scalars()}
    out = []
    for code, vals in hist.items():
        m = ms.get(code)
        last = vals[0]
        out.append({"code": code, "label": m.label if m else code, "workflow": m.workflow_code if m else None, "unit": m.unit if m else "", "formula": m.formula if m else None, "display": float(last.display_value) if last.display_value is not None else None, "previous": float(last.previous_value) if last.previous_value is not None else None, "changed": last.previous_value is not None and last.display_value != last.previous_value, "calcRunId": last.calc_run_id, "at": _iso(last.created_at), "history": [float(v.display_value) for v in reversed(vals) if v.display_value is not None]})
    return sorted(out, key=lambda x: (x["workflow"] or "", x["code"]))


@router.get("/monitor/calc/{cid}")
def monitor_calc_one(cid: str, session: Session = Depends(get_session)):
    c = session.get(CalcRun, cid)
    if not c:
        raise HTTPException(404, "계산 없음")
    return _calc_json(c)


@router.get("/monitor/artifacts")
def monitor_artifacts(session: Session = Depends(get_session)):
    rows = session.execute(select(ViewArtifact.key, ViewArtifact.generation, ViewArtifact.produced_by, ViewArtifact.workflow_run_id, ViewArtifact.created_at, ViewArtifact.changes).where(ViewArtifact.is_current).order_by(ViewArtifact.key)).all()
    return [{"key": k, "generation": g, "producedBy": p, "runId": r, "createdAt": _iso(c), "changes": len(ch or [])} for k, g, p, r, c, ch in rows]


@router.get("/monitor/artifacts/{key}")
def monitor_artifact(key: str, session: Session = Depends(get_session)):
    rows = session.execute(select(ViewArtifact).where(ViewArtifact.key == key).order_by(ViewArtifact.generation.desc()).limit(20)).scalars().all()
    if not rows:
        raise HTTPException(404, "산출물 없음")
    return {"key": key, "current": rows[0].payload, "generations": [{"generation": r.generation, "isCurrent": r.is_current, "producedBy": r.produced_by, "runId": r.workflow_run_id, "createdAt": _iso(r.created_at), "changes": r.changes} for r in rows]}


@router.get("/monitor/jobs")
def monitor_jobs(limit: int = 100, session: Session = Depends(get_session)):
    return [{"id": j.id, "workflow": j.workflow_code, "status": j.status, "runAfter": _iso(j.run_after), "attempts": j.attempts, "causes": j.causes, "lockedBy": j.locked_by, "createdAt": _iso(j.created_at), "finishedAt": _iso(j.finished_at), "error": j.error} for j in session.execute(select(Job).order_by(Job.id.desc()).limit(min(limit, 500))).scalars()]


@router.get("/settings-summary")
def settings_summary(session: Session = Depends(get_session)):
    return {s.key: s.value for s in session.execute(select(Setting)).scalars()}


# ═════════════════════════ 컬럼 정의서 (DCT-01~08) ═════════════════════════
BINDING_KINDS = ("metric", "base_ym", "const", "version", "insight", "proposal", "row", "dataset", "analysis", "evidence", "report", "plan", "unmapped")


def _contract_json(c) -> dict[str, Any]:
    return {"id": c.id, "table": c.table_code, "seq": c.seq, "column": c.column_name, "kor": c.kor_name, "isPk": c.is_pk, "type": c.data_type, "source": c.source_desc, "sourceColumn": c.source_column, "isMock": c.is_mock, "expected": c.expected_text, "binding": c.binding, "active": c.active, "workbook": c.workbook, "updatedAt": _iso(c.updated_at)}


@router.get("/contracts")
def contracts(session: Session = Depends(get_session)):
    from nhdip.contracts.materialize import mart_table
    from nhdip.models import ColumnContract
    from nhdip.views.store import get_current_row

    rows = session.execute(select(ColumnContract).order_by(ColumnContract.table_code, ColumnContract.seq)).scalars().all()
    tables: dict[str, dict[str, Any]] = {}
    for c in rows:
        t = tables.setdefault(c.table_code, {"code": c.table_code, "name": c.table_name, "dept": c.dept, "mart": f"mart.{mart_table(session, c.table_code, c.dept)}", "workbook": c.workbook, "columns": []})
        t["columns"].append(_contract_json(c))
    for code, t in tables.items():
        rep = get_current_row(session, f"contract.{code}")
        t["report"] = rep.payload if rep else None
        t["reportAt"] = _iso(rep.created_at) if rep else None
        t["reportRun"] = rep.workflow_run_id if rep else None
    metrics_ = [m.code for m in session.execute(select(Metric).where(Metric.enabled).order_by(Metric.code)).scalars()]
    # 정의서 적재 노드를 가진 워크플로우 — '다시 계산' 대상 (화면에 코드를 두지 않는다)
    nodes = session.execute(select(WorkflowNode).where(WorkflowNode.impl == "materialize_contracts", WorkflowNode.enabled).order_by(WorkflowNode.workflow_code)).scalars().all()
    by_table: dict[str, str] = {}
    for n in nodes:
        for code in (n.config or {}).get("tables") or list(tables):
            by_table.setdefault(code, n.workflow_code)
    for code, t in tables.items():
        t["workflow"] = by_table.get(code)
    builders = (session.get(Setting, "contracts.row_builders").value if session.get(Setting, "contracts.row_builders") else {}) or {}
    for code, t in tables.items():
        t["builder"] = builders.get(code)
    wf = nodes[0].workflow_code if nodes else None
    return {"tables": list(tables.values()), "metrics": metrics_, "bindingKinds": BINDING_KINDS, "workflow": next((n.workflow_code for n in nodes if "T01" in ((n.config or {}).get("tables") or [])), wf)}


@router.patch("/contracts/{cid}")
def contract_patch(cid: int, body: dict[str, Any], request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    from nhdip.models import ColumnContract

    c = session.get(ColumnContract, cid)
    if not c:
        raise HTTPException(404, "컬럼 없음")
    if "binding" in body:
        b = body["binding"] or {}
        if not isinstance(b, dict) or not any(k in b for k in BINDING_KINDS):
            raise HTTPException(422, f"바인딩 종류: {', '.join(BINDING_KINDS)}")
        if "metric" in b and not session.get(Metric, b["metric"]):
            raise HTTPException(422, f"지표 없음: {b['metric']}")
        c.binding = b
    if "active" in body:
        c.active = bool(body["active"])
    emit(session, "contract.changed", {"table": c.table_code, "column": c.column_name}, admin.emp_no)
    audit(session, admin.emp_no, "admin.contract.update", "contract", f"{c.table_code}.{c.column_name}", body, client_ip(request))
    session.commit()
    return _contract_json(c)


@router.post("/contracts/import")
async def contract_import(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """컬럼 정의서 엑셀 반영 — 기존 바인딩 유지, 새 컬럼은 기본 바인딩, 빠진 컬럼은 비활성."""
    from nhdip.contracts.materialize import import_workbook
    from nhdip.contracts.workbook import parse_workbook
    from nhdip.seed.defs_contracts import BINDINGS
    from nhdip.seed.defs_dept_contracts import BINDINGS as DEPT_BINDINGS

    _, content = await _read(file, "contract", session, request, admin.emp_no)
    prefixes = (session.get(Setting, "contracts.dept_prefix").value if session.get(Setting, "contracts.dept_prefix") else None) or {"종기부": "hq"}
    raw = (session.get(Setting, "contracts.raw_depts").value if session.get(Setting, "contracts.raw_depts") else None) or ["종기부"]
    try:
        tables = parse_workbook(content, prefixes, raw)
    except Exception as exc:  # noqa: BLE001 — 형식 오류는 사용자에게
        raise HTTPException(422, f"엑셀을 읽을 수 없습니다(DRM 암호화 파일은 해제 후 업로드): {exc}") from exc
    if not tables:
        raise HTTPException(422, "정의서 시트가 없습니다 — 시트명 'T01_부서_이름', 헤더 '컬럼명' 행이 필요합니다")
    invalid = [f"{t['table_code']}.{c['column_name']}" for t in tables for c in t["columns"] if not c["valid_name"]]
    unknown = sorted({t["dept"] for t in tables if t["dept"] not in prefixes})
    if unknown:
        raise HTTPException(422, f"부서 접두가 없습니다: {', '.join(unknown)} — 설정 contracts.dept_prefix 에 추가 후 다시 올려 주세요")
    res = import_workbook(session, tables, file.filename or "upload.xlsx", {**BINDINGS, **DEPT_BINDINGS}, admin.emp_no)
    emit(session, "contract.changed", {"workbook": file.filename, **res}, admin.emp_no)
    audit(session, admin.emp_no, "admin.contract.import", "contract", file.filename, {**res, "invalid": invalid}, client_ip(request))
    session.commit()
    return {**res, "invalidColumns": invalid}


@router.get("/contracts/{code}/rows")
def contract_rows(code: str, limit: int = 50, session: Session = Depends(get_session)):
    from sqlalchemy import text as sql

    from nhdip.contracts.materialize import mart_table
    from nhdip.models import ColumnContract

    c = session.execute(select(ColumnContract).where(ColumnContract.table_code == code).limit(1)).scalar()
    if not c:
        raise HTTPException(404, "정의서 테이블 없음")
    table = mart_table(session, code, c.dept)
    exists = session.execute(sql("SELECT 1 FROM information_schema.tables WHERE table_schema='mart' AND table_name=:t"), {"t": table}).first()
    if not exists:
        return {"table": f"mart.{table}", "columns": [], "rows": []}
    rs = session.execute(sql(f'SELECT * FROM mart."{table}" ORDER BY _generated_at DESC LIMIT :n'), {"n": min(limit, 500)})
    cols = list(rs.keys())
    return {"table": f"mart.{table}", "columns": cols, "rows": [{k: (str(v) if v is not None and not isinstance(v, (str, int, float)) else v) for k, v in zip(cols, r)} for r in rs]}


# ═════════════════════════ 추적 (작업 0.5 · NFR-09) ═════════════════════════
def _ms(a, b) -> int | None:
    return round((b - a).total_seconds() * 1000) if a and b else None


@router.get("/monitor/traces")
def monitor_traces(limit: int = 50, session: Session = Depends(get_session)):
    """최근 추적 — 기록된 HTTP 요청(변경 · 오류 · 느린 조회) 기준."""
    rows = session.execute(select(RequestLog).order_by(RequestLog.id.desc()).limit(min(limit, 300))).scalars().all()
    return [{"traceId": r.trace_id, "at": _iso(r.at), "method": r.method, "path": r.path, "route": r.route, "status": r.status, "durationMs": r.duration_ms, "dbQueries": r.db_queries, "dbMs": r.db_ms, "actor": r.actor} for r in rows]


@router.get("/monitor/trace/{trace_id}")
def monitor_trace(trace_id: str, session: Session = Depends(get_session)):
    """단일 추적 ID 의 전 구간 — HTTP 요청 → 감사 → 변경 이벤트 → 워크플로우 실행(노드 · 계산 · LLM · DB) 시간순."""
    import re

    tid = trace_id.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", tid):
        raise HTTPException(422, "추적 ID 는 32자리 16진수입니다")
    spans: list[dict[str, Any]] = []
    for r in session.execute(select(RequestLog).where(RequestLog.trace_id == tid).order_by(RequestLog.at)).scalars():
        spans.append({"kind": "http", "at": _iso(r.at), "label": f"{r.method} {r.route or r.path}", "path": r.path, "status": r.status, "durationMs": r.duration_ms, "db": {"queries": r.db_queries, "ms": r.db_ms}, "actor": r.actor})
    for a in session.execute(select(AuditLog).where(AuditLog.trace_id == tid).order_by(AuditLog.at)).scalars():
        spans.append({"kind": "audit", "at": _iso(a.at), "label": a.action, "actor": a.actor, "target": f"{a.target_kind or ''} {a.target_id or ''}".strip(), "detail": a.detail})
    for e in session.execute(select(OutboxEvent).where(OutboxEvent.trace_id == tid).order_by(OutboxEvent.id)).scalars():
        spans.append({"kind": "event", "at": _iso(e.created_at), "label": e.type, "eventId": e.id, "actor": e.actor, "payload": e.payload, "matched": [m.get("workflow") for m in (e.matched or [])], "dispatchedAt": _iso(e.dispatched_at)})
    runs = session.execute(
        select(WorkflowRun).where((WorkflowRun.trace_id == tid) | WorkflowRun.causes.contains([{"trace_id": tid}])).order_by(WorkflowRun.started_at)
    ).scalars().all()
    run_ids = [r.id for r in runs]
    for r in runs:
        nodes = session.execute(select(NodeRun).where(NodeRun.workflow_run_id == r.id).order_by(NodeRun.seq)).scalars().all()
        calcs = session.execute(select(func.count()).select_from(CalcRun).where(CalcRun.workflow_run_id == r.id)).scalar()
        spans.append({
            "kind": "run", "at": _iso(r.started_at), "label": r.workflow_code, "runId": r.id, "status": r.status,
            "durationMs": _ms(r.started_at, r.finished_at), "db": (r.summary or {}).get("obs"), "calcRuns": calcs,
            "merged": r.trace_id != tid,  # 다른 변경과 병합되어 실행된 경우
            "nodes": [{"key": n.node_key, "status": n.status, "durationMs": n.duration_ms} for n in nodes],
        })
    q = select(LlmCall).where(LlmCall.trace_id == tid)
    if run_ids:
        q = select(LlmCall).where((LlmCall.trace_id == tid) | LlmCall.workflow_run_id.in_(run_ids))
    for c in session.execute(q.order_by(LlmCall.created_at)).scalars():
        spans.append({"kind": "llm", "at": _iso(c.created_at), "label": f"{c.agent_code or '-'} · {c.purpose}", "callId": c.id, "runId": c.workflow_run_id, "status": c.status, "durationMs": c.latency_ms, "model": c.model, "tokens": (c.prompt_tokens or 0) + (c.completion_tokens or 0)})
    order = {"http": 0, "audit": 1, "event": 2, "run": 3, "llm": 4}
    spans.sort(key=lambda x: (x["at"] or "", order[x["kind"]]))
    if not spans:
        raise HTTPException(404, "이 추적 ID 로 기록된 구간이 없습니다")
    return {"traceId": tid, "spans": spans}


# ═════════════════════════ 골든셋 평가 (작업 8.1) ═════════════════════════
@router.post("/evals/run")
def evals_run(request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """골든셋 평가를 지금 실행하고 결과를 산출물(eval.golden)로 남긴다."""
    from nhdip.evals import run as run_eval
    from nhdip.views.store import publish

    rep = run_eval(session)
    publish(session, "eval.golden", rep, produced_by=f"admin:{admin.emp_no}")
    audit(session, admin.emp_no, "admin.eval.run", "eval", "golden", {"passed": rep["passed"], "rates": {k: v["rate"] for k, v in rep["categories"].items()}}, client_ip(request))
    session.commit()
    return rep


@router.get("/evals/latest")
def evals_latest(session: Session = Depends(get_session)):
    from nhdip.views.store import get_current

    rep = get_current(session, "eval.golden")
    if rep is None:
        raise HTTPException(404, "평가 결과 없음 — 먼저 실행하세요")
    return rep


# ═════════════════════════ 에이전트 결정 · 구성 (B.30) ═════════════════════════
@router.get("/agents/decisions")
def agent_decisions(agent: str | None = None, workflow: str | None = None, run: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    """오케스트레이터 · 변화 감지 · 플래너 · 서술 에이전트의 결정과 근거."""
    from nhdip.models import AgentDecision

    q = select(AgentDecision).order_by(AgentDecision.id.desc()).limit(min(max(limit, 1), 500))
    if agent:
        q = q.where(AgentDecision.agent_code == agent)
    if workflow:
        q = q.where(AgentDecision.workflow_code == workflow)
    if run:
        q = q.where(AgentDecision.workflow_run_id == run)
    counts = dict(session.execute(select(AgentDecision.agent_code, func.count()).group_by(AgentDecision.agent_code)).all())
    return {
        "counts": counts,
        "items": [{"id": d.id, "at": _iso(d.at), "agent": d.agent_code, "workflow": d.workflow_code, "jobId": d.job_id, "runId": d.workflow_run_id, "decision": d.decision, "summary": d.summary, "detail": d.detail, "traceId": d.trace_id} for d in session.execute(q).scalars()],
    }


@router.get("/pipeline")
def pipeline(session: Session = Depends(get_session)):
    """파이프라인 화면 (B.39) — 원천 → 워크플로우(노드 · 에이전트 · 실행) → 산출물 → 화면."""
    from .pipeline_view import build_pipeline

    return build_pipeline(session)


@router.get("/agents/topology")
def agent_topology(session: Session = Depends(get_session)):
    """워크플로우별 에이전트 배치(노드 순서) + 오케스트레이터 의존 그래프."""
    from nhdip.models import Agent
    from nhdip.workflow.orchestrator import dependency_graph, policy as orch_policy

    agents = {a.code: {"code": a.code, "name": a.name, "role": a.role, "kind": a.kind, "enabled": a.enabled} for a in session.execute(select(Agent)).scalars()}
    flows = []
    for w in session.execute(select(Workflow).order_by(Workflow.sort)).scalars():
        nodes = session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == w.code).order_by(WorkflowNode.seq)).scalars().all()
        flows.append({"code": w.code, "name": w.name, "enabled": w.enabled, "nodes": [{"key": n.key, "name": n.name, "impl": n.impl, "agent": n.agent_code, "enabled": n.enabled} for n in nodes]})
    return {"agents": list(agents.values()), "workflows": flows, "orchestrator": {"policy": orch_policy(session), "depends_on": dependency_graph(session)}}


# ═════════════════════════ 운영 알림 · LLM 비용 (작업 8.5 · 4.7) ═════════════════════════
@router.get("/alerts")
def alerts_list(limit: int = 100, session: Session = Depends(get_session)):
    from nhdip.alerts import policy
    from nhdip.models.runtime import Alert

    rows = session.execute(select(Alert).order_by(Alert.id.desc()).limit(min(limit, 500))).scalars().all()
    import os

    channels = {"webhook": bool(os.environ.get("ALERT_WEBHOOK_URL")), "email": bool(os.environ.get("ALERT_SMTP_HOST") and os.environ.get("ALERT_SMTP_TO"))}
    return {
        "policy": policy(session),
        "channelsConfigured": channels,
        "items": [{"id": a.id, "at": _iso(a.at), "kind": a.kind, "severity": a.severity, "title": a.title, "detail": a.detail, "status": a.status, "channels": a.channels, "traceId": a.trace_id} for a in rows],
    }


@router.post("/alerts/test")
def alerts_test(request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    """시험 알림 — 꺼져 있어도 설정된 채널로 1건 보낸다(채널 점검)."""
    from nhdip.alerts import raise_alert

    a = raise_alert(session, "test", "warning", "시험 알림 — 운영 알림 채널 점검", {"by": admin.emp_no}, f"test:{utcnow().isoformat()}", force=True)
    audit(session, admin.emp_no, "admin.alert.test", "alert", str(a.id), {"status": a.status, "channels": a.channels}, client_ip(request))
    session.commit()
    return {"id": a.id, "status": a.status, "channels": a.channels}


@router.post("/alerts/scan")
def alerts_scan(request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    from nhdip.alerts import scan

    created = scan(session)
    audit(session, admin.emp_no, "admin.alert.scan", "alert", None, {"created": created}, client_ip(request))
    session.commit()
    return {"created": created}


@router.get("/llm/usage")
def llm_usage(session: Session = Depends(get_session)):
    """이번 달 LLM 사용량(토큰 · 금액) · 예산 대비."""
    from nhdip.llm.budget import status

    return status(session)
