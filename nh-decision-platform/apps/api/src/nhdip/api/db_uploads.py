"""업무 자료 등록 요청 · 관리자 승인 (Phase C · UPL-01~03 · Q99).

- 업무 사용자(화면 리소스 `db_upload`)는 [데이터베이스]에서 정형 자료(기존 데이터셋의 새 버전)나 문서를 올린다.
  올리는 즉시 업로드 보안 검사 · 형식 · 품질 검사를 하고(저장 · 이벤트 없음) 결과와 함께 '승인 대기' 요청으로 남긴다.
  품질 실패 자료는 요청 단계에서 거절한다.
- 관리자가 승인하면 관리자 직접 업로드와 같은 확정 경로(`ingest_file` · `ingest_document`)를 탄다 → 현재 버전 · 이벤트 · 관련 워크플로.
  반려는 사유 필수, 아무 데이터도 바뀌지 않는다.
- 감사: `db.upload.request` · `db.upload.approve` | `db.upload.reject` · `db.upload.applied` | `db.upload.failed`.
- 올릴 수 있는 대상은 설정 `upload.user_targets` (`{"datasets": "*" | [코드…], "doc_classes": "*" | [분류…]}`).
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.data.datasets import IngestError, check_file, current_versions, ingest_file
from nhdip.data.documents import DocumentError, extract_text, ingest_document
from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser, Dataset, OrgUnit, Setting, UploadRequest, utcnow

from .admin_data import _read as read_upload
from .deps import client_ip, current_user, require_admin, require_resource

router = APIRouter(tags=["db"])
admin_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_DEFAULT_TARGETS: dict[str, Any] = {"datasets": "*", "doc_classes": "*"}
STATUS_LABEL = {"pending": "승인 대기", "approved": "승인 · 반영", "rejected": "반려", "failed": "반영 실패"}


def _iso(v):
    return v.isoformat() if v else None


def _targets(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "upload.user_targets")
    v = s.value if s is not None and isinstance(s.value, dict) else {}
    return {**_DEFAULT_TARGETS, **v}


def _allowed(spec: Any, key: str) -> bool:
    return spec == "*" or (isinstance(spec, list) and key in spec)


def _doc_classes(session: Session) -> list[dict[str, str]]:
    labels = session.get(Setting, "doc_class.labels")
    origins = session.get(Setting, "doc_class.default_origin")
    lab = labels.value if labels is not None and isinstance(labels.value, dict) else {}
    org = origins.value if origins is not None and isinstance(origins.value, dict) else {}
    allow = _targets(session)["doc_classes"]
    return [{"key": k, "label": str(v), "origin": str(org.get(k, "bank"))} for k, v in lab.items() if _allowed(allow, k)]


def _store(user: str, name: str, content: bytes) -> tuple[str, str]:
    """요청 파일은 파일 저장소 `requests/` 에 둔다(승인 때 다시 읽음). 저장소에 쓸 수 없으면 요청을 받지 않는다(503)."""
    sha = hashlib.sha256(content).hexdigest()
    base = os.path.join(get_settings().filestore_dir, "requests")
    safe = re.sub(r"[^0-9A-Za-z가-힣._()\-]+", "_", os.path.basename(name))[:120] or "upload"
    path = os.path.join(base, f"{sha[:16]}_{user}_{safe}")
    try:
        os.makedirs(base, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        raise HTTPException(503, "파일 저장소에 쓸 수 없어 요청을 받지 못했습니다 — 관리자에게 알려 주세요(FILESTORE_DIR 권한, 관리자 [시스템 상태] 운영 준비 점검)") from exc
    return sha, path


def _names(session: Session, emps: set[str]) -> dict[str, str]:
    if not emps:
        return {}
    return dict(session.execute(select(AppUser.emp_no, AppUser.name).where(AppUser.emp_no.in_(emps))).all())


def _req_json(r: UploadRequest, names: dict[str, str] | None = None, orgs: dict[str, str] | None = None, full: bool = False) -> dict[str, Any]:
    names = names or {}
    out = {
        "id": r.id,
        "kind": r.kind,
        "target": r.target,
        "targetLabel": (r.meta or {}).get("targetLabel") or r.target,
        "origin": r.origin,
        "fileName": r.file_name,
        "meta": {k: v for k, v in (r.meta or {}).items() if k != "text"},
        "preview": {k: v for k, v in (r.preview or {}).items() if full or k != "sample"},
        "status": r.status,
        "statusLabel": STATUS_LABEL.get(r.status, r.status),
        "requestedBy": r.requested_by,
        "requestedByName": names.get(r.requested_by),
        "requestedOrg": r.requested_org,
        "requestedOrgName": (orgs or {}).get(r.requested_org or ""),
        "reviewedBy": r.reviewed_by,
        "reviewedByName": names.get(r.reviewed_by or ""),
        "reviewedAt": _iso(r.reviewed_at),
        "reviewNote": r.review_note,
        "result": r.result or {},
        "createdAt": _iso(r.created_at),
    }
    return out


def _dataset_for_user(session: Session, code: str) -> Dataset:
    d = session.get(Dataset, code)
    if d is None or not getattr(d, "active", True):
        raise HTTPException(404, "데이터셋 없음")
    if not _allowed(_targets(session)["datasets"], code):
        raise HTTPException(403, "이 데이터셋은 업무 화면에서 올릴 수 없습니다 — 관리자에게 요청하세요")
    return d


# ═════════════════════════ 업무 사용자 ═════════════════════════
@router.get("/db/uploadable")
def uploadable(user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    """올릴 수 있는 데이터셋(현재 버전 요약) · 문서 분류 · 파일 형식."""
    allow = _targets(session)["datasets"]
    out = []
    for d in session.execute(select(Dataset).order_by(Dataset.origin, Dataset.code)).scalars():
        if not getattr(d, "active", True) or not _allowed(allow, d.code):
            continue
        cur = current_versions(session, d)
        out.append({
            "code": d.code, "name": d.name, "origin": d.origin, "kind": d.kind, "description": d.description,
            "filePattern": d.file_pattern, "refreshCycle": d.refresh_cycle,
            "columns": [{"name": c.get("name"), "label": c.get("label") or c.get("description") or "", "type": c.get("type")} for c in (d.columns or [])][:60],
            "current": [{"version": v.version, "asOf": _iso(v.as_of), "rows": v.row_count, "dataOrigin": v.data_origin} for v in cur[:3]],
        })
    return {"datasets": out, "docClasses": _doc_classes(session), "accept": {"dataset": ".csv,.tsv,.xlsx,.json", "document": ".pdf,.hwpx,.hwp,.txt,.md,.html"}}


@router.post("/db/uploads/dataset", status_code=201)
async def request_dataset(
    request: Request,
    target: str = Form(...),
    file: UploadFile = File(...),
    data_origin: str = Form("actual"),
    as_of: str | None = Form(None),
    note: str | None = Form(None),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    d = _dataset_for_user(session, target)
    if data_origin not in ("actual", "simulated"):
        raise HTTPException(422, "data_origin 은 actual | simulated")
    if as_of and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise HTTPException(422, "기준일은 YYYY-MM-DD 형식입니다")
    name, content = await read_upload(file, "dataset", session, request, user.emp_no)
    try:
        pv = check_file(session, d, name, content)
    except (IngestError, ValueError) as exc:
        raise HTTPException(422, f"파일을 읽을 수 없습니다 — {exc}") from exc
    q = pv["quality"]
    if q.get("status") == "failed":
        bad = [f"{c['rule']}: {c['detail']}" for c in q.get("checks", []) if not c.get("passed") and c.get("severity") == "error"][:5]
        audit(session, user.emp_no, "db.upload.rejected_quality", "dataset", d.code, {"file": name, "checks": bad}, client_ip(request))
        session.commit()
        raise HTTPException(422, "품질 검사를 통과하지 못해 요청하지 않았습니다 — " + " · ".join(bad))
    sha, path = _store(user.emp_no, name, content)
    r = UploadRequest(
        kind="dataset", target=d.code, origin=d.origin, file_name=name, file_path=path, file_sha256=sha,
        meta={"targetLabel": d.name, "asOf": as_of or None, "dataOrigin": data_origin, "note": (note or "")[:500]},
        preview={"rows": pv["rows"], "quality": {"status": q.get("status"), "checks": q.get("checks", []), "source": q.get("source")}, "headers": pv["headers"][:60], "columns": pv["columns"][:60], "sample": pv["sample"]},
        status="pending", requested_by=user.emp_no, requested_org=user.org_code,
    )
    session.add(r)
    session.flush()
    audit(session, user.emp_no, "db.upload.request", "upload_request", str(r.id), {"kind": "dataset", "target": d.code, "file": name, "rows": pv["rows"], "quality": q.get("status")}, client_ip(request))
    session.commit()
    return _req_json(r, full=True)


@router.post("/db/uploads/document", status_code=201)
async def request_document(
    request: Request,
    doc_class: str = Form(...),
    title: str = Form(...),
    issuer: str | None = Form(None),
    published_at: str | None = Form(None),
    text: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    classes = {c["key"]: c for c in _doc_classes(session)}
    if doc_class not in classes:
        raise HTTPException(422, "올릴 수 없는 문서 분류입니다")
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise HTTPException(422, "제목은 1~200자입니다")
    if published_at and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_at):
        raise HTTPException(422, "시행일은 YYYY-MM-DD 형식입니다")
    if file is not None and file.filename:
        name, content = await read_upload(file, "document", session, request, user.emp_no)
    elif (text or "").strip():
        name, content = f"{re.sub(r'[^0-9A-Za-z가-힣]+', '_', title)[:60] or 'document'}.txt", (text or "").encode("utf-8")
    else:
        raise HTTPException(422, "파일이나 본문을 넣어 주세요")
    try:
        body, pages = extract_text(name, content)
    except (DocumentError, ValueError) as exc:
        raise HTTPException(422, f"본문을 읽을 수 없습니다 — {exc}") from exc
    if not (body or "").strip():
        raise HTTPException(422, "본문 텍스트가 비어 있습니다(스캔 PDF 는 OCR 후 올려 주세요)")
    sha, path = _store(user.emp_no, name, content)
    cls = classes[doc_class]
    r = UploadRequest(
        kind="document", target=doc_class, origin=cls["origin"], file_name=name, file_path=path, file_sha256=sha,
        meta={"targetLabel": cls["label"], "title": title, "issuer": (issuer or "")[:120] or None, "publishedAt": published_at or None, "note": (note or "")[:500]},
        preview={"chars": len(body), "pages": len(pages or []) or 1, "excerpt": body.strip()[:400]},
        status="pending", requested_by=user.emp_no, requested_org=user.org_code,
    )
    session.add(r)
    session.flush()
    audit(session, user.emp_no, "db.upload.request", "upload_request", str(r.id), {"kind": "document", "target": doc_class, "title": title, "file": name}, client_ip(request))
    session.commit()
    return _req_json(r, full=True)


@router.get("/db/uploads/mine")
def my_uploads(user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    rows = session.execute(select(UploadRequest).where(UploadRequest.requested_by == user.emp_no).order_by(UploadRequest.id.desc()).limit(50)).scalars().all()
    names = _names(session, {r.reviewed_by for r in rows if r.reviewed_by})
    return [_req_json(r, names) for r in rows]


# ═════════════════════════ 검토(관리자 · 부서 데이터 책임자) ═════════════════════════
class ReviewIn(BaseModel):
    note: str | None = None
    force: bool = False


def _pending(session: Session, rid: int) -> UploadRequest:
    r = session.get(UploadRequest, rid, with_for_update=True)
    if r is None:
        raise HTTPException(404, "요청 없음")
    if r.status != "pending":
        raise HTTPException(409, f"이미 처리된 요청입니다 ({STATUS_LABEL.get(r.status, r.status)})")
    return r


def _list(session: Session, q, full: bool = True) -> list[dict[str, Any]]:
    rows = session.execute(q).scalars().all()
    names = _names(session, {r.requested_by for r in rows} | {r.reviewed_by for r in rows if r.reviewed_by})
    orgs = dict(session.execute(select(OrgUnit.code, OrgUnit.name).where(OrgUnit.code.in_({r.requested_org for r in rows if r.requested_org}))).all()) if rows else {}
    return [_req_json(r, names, orgs, full=full) for r in rows]


def _counts(session: Session, where=None) -> dict[str, int]:
    counts = {k: 0 for k in STATUS_LABEL}
    q = select(UploadRequest.status)
    if where is not None:
        q = q.where(where)
    for (st,) in session.execute(q).all():
        counts[st] = counts.get(st, 0) + 1
    return counts


def do_approve(session: Session, r: UploadRequest, actor: AppUser, body: ReviewIn, ip: str | None, via: str) -> dict[str, Any]:
    """승인 — 관리자 직접 업로드와 같은 확정 경로(저장점 안). 실패하면 요청만 failed 로 남긴다."""
    try:
        with open(r.file_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        raise HTTPException(410, "요청 파일을 찾을 수 없습니다 — 다시 올려 달라고 요청하세요") from exc
    if r.file_sha256 and hashlib.sha256(content).hexdigest() != r.file_sha256:
        raise HTTPException(409, "요청 파일이 바뀌었습니다(해시 불일치) — 반려 후 다시 올려 달라고 요청하세요")
    meta = r.meta or {}
    note = f"업무 자료 요청 #{r.id} ({r.requested_by}) 승인" + (" · 부서 데이터 책임자" if via == "steward" else "") + (f" — {meta.get('note')}" if meta.get("note") else "")
    sp = session.begin_nested()
    try:
        if r.kind == "dataset":
            d = session.get(Dataset, r.target)
            if d is None:
                raise IngestError("데이터셋이 없어졌습니다")
            v = ingest_file(session, d, r.file_name, content, as_of=meta.get("asOf") or None, data_origin=meta.get("dataOrigin") or "actual", actor=actor.emp_no, note=note, force=bool(body.force))
            result = {"version": v.version, "versionId": v.id, "status": v.status, "rows": v.row_count, "quality": (v.quality or {}).get("status"), "isCurrent": v.is_current}
            if v.status != "committed":
                raise IngestError(f"품질 검사 실패로 확정되지 않았습니다(v{v.version}) — 필요하면 '품질 실패여도 확정' 으로 승인")
        else:
            title = str(meta.get("title") or r.file_name)
            code = "doc-" + re.sub(r"[^0-9A-Za-z가-힣]+", "-", title)[:60].strip("-").lower()
            doc = ingest_document(
                session, origin=r.origin, doc_code=code, title=title, doc_class=r.target, filename=r.file_name, content=content,
                issuer=meta.get("issuer"), published_at=meta.get("publishedAt"),
                meta={"docType": "업무 등록 문서", "isOfficial": r.origin == "ext", "requestedBy": r.requested_by, "uploadRequest": r.id}, actor=actor.emp_no,
            )
            result = {"documentId": doc.id, "docCode": doc.doc_code, "version": doc.version, "origin": r.origin}
        sp.commit()
    except (IngestError, DocumentError, ValueError) as exc:
        sp.rollback()
        r.status, r.result = "failed", {"error": str(exc)[:500]}
        r.reviewed_by, r.reviewed_at, r.review_note = actor.emp_no, utcnow(), body.note
        audit(session, actor.emp_no, "db.upload.failed", "upload_request", str(r.id), {"error": str(exc)[:300], "via": via}, ip)
        session.commit()
        raise HTTPException(422, f"반영하지 못했습니다 — {exc}") from exc
    r.status, r.result = "approved", {**result, "via": via}
    r.reviewed_by, r.reviewed_at, r.review_note = actor.emp_no, utcnow(), body.note
    audit(session, actor.emp_no, "db.upload.approve", "upload_request", str(r.id), {"kind": r.kind, "target": r.target, "requestedBy": r.requested_by, "note": body.note, "via": via}, ip)
    audit(session, actor.emp_no, "db.upload.applied", "upload_request", str(r.id), result, ip)
    session.commit()
    return _req_json(r, full=True)


def do_reject(session: Session, r: UploadRequest, actor: AppUser, body: ReviewIn, ip: str | None, via: str) -> dict[str, Any]:
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(422, "반려 사유를 적어 주세요")
    r.status = "rejected"
    r.reviewed_by, r.reviewed_at, r.review_note = actor.emp_no, utcnow(), note[:1000]
    audit(session, actor.emp_no, "db.upload.reject", "upload_request", str(r.id), {"kind": r.kind, "target": r.target, "requestedBy": r.requested_by, "note": note[:300], "via": via}, ip)
    session.commit()
    return _req_json(r, full=True)


# ── 관리자 — 전체 요청 ──
@admin_router.get("/uploads")
def admin_uploads(status: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    q = select(UploadRequest).order_by(UploadRequest.id.desc()).limit(min(max(limit, 1), 300))
    if status:
        q = q.where(UploadRequest.status == status)
    return {"items": _list(session, q), "counts": _counts(session)}


@admin_router.post("/uploads/{rid}/approve")
def approve_upload(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    return do_approve(session, _pending(session, rid), admin, body, client_ip(request), "admin")


@admin_router.post("/uploads/{rid}/reject")
def reject_upload(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if not (body.note or "").strip():
        raise HTTPException(422, "반려 사유를 적어 주세요")
    return do_reject(session, _pending(session, rid), admin, body, client_ip(request), "admin")


# ── 부서 데이터 책임자 — 자기 부서 사용자의 요청만 · 본인 요청은 다른 책임자 · 관리자가 (UPL-04 · Q107) ──
def _steward(user: AppUser = Depends(current_user)) -> AppUser:
    if not user.data_steward:
        raise HTTPException(403, "부서 데이터 책임자만 볼 수 있습니다 — 관리자 [사용자]에서 지정")
    return user


def _scope_orgs(session: Session, steward: AppUser) -> tuple[OrgUnit | None, set[str]]:
    """책임자 부서와 그 아래 조직 코드 전체."""
    from nhdip.orgs import steward_scope

    scope = steward_scope(session, steward.org_code)
    if scope is None:
        return None, set()
    out, frontier = {scope.code}, [scope.code]
    while frontier:
        kids = session.execute(select(OrgUnit.code).where(OrgUnit.parent_code.in_(frontier))).scalars().all()
        frontier = [k for k in kids if k not in out]
        out.update(frontier)
    return scope, out


@router.get("/db/uploads/review")
def steward_review(status: str | None = "pending", session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    scope, orgs = _scope_orgs(session, user)
    where = UploadRequest.requested_org.in_(orgs or {"-"})
    q = select(UploadRequest).where(where).order_by(UploadRequest.id.desc()).limit(100)
    if status:
        q = q.where(UploadRequest.status == status)
    items = _list(session, q)
    for it in items:
        it["canReview"] = it["status"] == "pending" and it["requestedBy"] != user.emp_no
    return {"scope": {"code": scope.code, "name": scope.name} if scope else None, "items": items, "counts": _counts(session, where)}


def _steward_pending(session: Session, rid: int, user: AppUser) -> UploadRequest:
    from nhdip.orgs import in_steward_scope

    r = _pending(session, rid)
    if not in_steward_scope(session, user, r.requested_org):
        raise HTTPException(404, "요청 없음")  # 다른 부서 요청은 없는 것처럼
    if r.requested_by == user.emp_no:
        raise HTTPException(409, "본인이 올린 자료는 다른 책임자나 관리자가 승인해야 합니다")
    return r


@router.post("/db/uploads/{rid}/approve")
def steward_approve(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    return do_approve(session, _steward_pending(session, rid, user), user, body, client_ip(request), "steward")


@router.post("/db/uploads/{rid}/reject")
def steward_reject(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    if not (body.note or "").strip():
        raise HTTPException(422, "반려 사유를 적어 주세요")
    return do_reject(session, _steward_pending(session, rid, user), user, body, client_ip(request), "steward")


def steward_pending_count(session: Session, user: AppUser) -> int:
    """사이드바 건수 — 책임자 부서의 승인 대기(본인 요청 제외)."""
    if not getattr(user, "data_steward", False):
        return 0
    _, orgs = _scope_orgs(session, user)
    if not orgs:
        return 0
    from sqlalchemy import func

    return int(session.execute(select(func.count()).select_from(UploadRequest).where(UploadRequest.status == "pending", UploadRequest.requested_org.in_(orgs), UploadRequest.requested_by != user.emp_no)).scalar() or 0)
