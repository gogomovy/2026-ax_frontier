"""관리자 API — 업무 구성 파일 (Phase O · BIZ-02 · BIZ-05) · 맞는 자료로 자동 올리기.

데이터 관리자만 반영 · 삭제한다(구성은 지표 · 규칙 · 화면 연결을 한꺼번에 바꾼다). 모두 감사 기록을 남긴다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.bizconfig.apply import apply, preview, remove
from nhdip.bizconfig.bundle import BundleError, read_bundle, write_bundle
from nhdip.db import get_session
from nhdip.events import audit, emit
from nhdip.models import AppUser, BusinessConfig, Dataset

from .admin_data import _read
from .deps import client_ip, require_admin, require_data_admin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _json(c: BusinessConfig, full: bool = False) -> dict[str, Any]:
    b = c.content or {}
    out = {
        "id": c.id, "name": c.name, "version": c.version, "status": c.status, "fileName": c.file_name, "sha256": c.sha256, "uploadedBy": c.uploaded_by,
        "createdAt": c.created_at.isoformat() if c.created_at else None, "description": b.get("description") or "",
        "counts": {k: len(b.get(k) or []) for k in ("sources", "metrics", "workflows", "bindings", "artifacts", "rules", "orgs", "screens", "settings", "contracts")},
        "report": c.report or {},
    }
    if full:
        out["content"] = b
    return out


async def _bundle(file: UploadFile, session: Session, request: Request, actor: str) -> tuple[str, bytes, dict[str, Any]]:
    name, content = await _read(file, "dataset", session, request, actor)
    try:
        return name, content, read_bundle(name, content)
    except BundleError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/business-config")
def list_configs(all: bool = False, session: Session = Depends(get_session)):
    q = select(BusinessConfig).order_by(BusinessConfig.name, BusinessConfig.version.desc())
    if not all:
        q = q.where(BusinessConfig.status == "active")
    from nhdip.data.sources import Resolver

    status = Resolver(session).status()
    return {"items": [_json(c) for c in session.execute(q).scalars()], "sources": status,
            "linked": sum(1 for s in status if s["status"] == "linked"), "waiting": sum(1 for s in status if s["status"] == "waiting")}


@router.get("/business-config/sources")
def config_sources(session: Session = Depends(get_session)):
    """자료 이름 → 지금 이어진 데이터셋(연결됨 · 자료 대기 — 가장 가까운 정의와 없는 열)."""
    from nhdip.data.sources import Resolver

    return Resolver(session).status()


@router.post("/business-config/preview")
async def config_preview(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session), admin: AppUser = Depends(require_data_admin)):
    _, _, b = await _bundle(file, session, request, admin.emp_no)
    out = preview(session, b)
    session.rollback()
    return out


@router.post("/business-config", status_code=201)
async def config_apply(request: Request, file: UploadFile = File(...), session: Session = Depends(get_session), admin: AppUser = Depends(require_data_admin)):
    name, content, b = await _bundle(file, session, request, admin.emp_no)
    try:
        cfg = apply(session, b, actor=admin.emp_no, file_name=name, content=content)
    except BundleError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return _json(cfg)


@router.get("/business-config/{cid}")
def config_get(cid: int, session: Session = Depends(get_session)):
    c = session.get(BusinessConfig, cid)
    if c is None:
        raise HTTPException(404, "업무 구성 없음")
    return _json(c, full=True)


@router.get("/business-config/{cid}/download")
def config_download(cid: int, session: Session = Depends(get_session)):
    from fastapi.responses import Response

    c = session.get(BusinessConfig, cid)
    if c is None:
        raise HTTPException(404, "업무 구성 없음")
    return Response(write_bundle(c.content or {}), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''business-config-{c.id}.xlsx"})


class RemoveIn(BaseModel):
    reason: str


@router.post("/business-config/{cid}/delete")
def config_delete(cid: int, body: RemoveIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_data_admin)):
    from nhdip.data.deletion import DeleteError, clean_reason

    c = session.get(BusinessConfig, cid)
    if c is None:
        raise HTTPException(404, "업무 구성 없음")
    try:
        reason = clean_reason(body.reason)
        out = remove(session, c, actor=admin.emp_no, reason=reason)
    except (BundleError, DeleteError) as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    session.commit()
    return {"id": c.id, "status": c.status, "removed": out}


# ═════════════════════════ 맞는 자료로 자동 올리기 (시연 자료 · 시험 · 여러 파일) ═════════════════════════
@router.post("/datasets/auto-upload", status_code=201)
async def dataset_auto_upload(
    request: Request,
    file: UploadFile = File(...),
    origin: str = Form("bank"),
    data_origin: str = Form("actual"),
    note: str | None = Form(None),
    force: bool = Form(False),
    owner_org: str | None = Form(None),
    common: bool = Form(False),
    session: Session = Depends(get_session),
    admin: AppUser = Depends(require_admin),
):
    """대상 없이 올리기 — 맞는 정의(파일 이름 규칙 · 열 구성)가 있으면 그 자료의 새 버전, 없으면 파일에서 정의를 만들어 첫 버전(한 트랜잭션).
    owner_org = 자료를 둘 팀 · 영업점(빈 값 = 전행 공통). common = 공통 통합 DB 로 올림(새 정의면 공통으로 만든다 · 소유 팀 없음, §38 CMN)."""
    from nhdip.data.datasets import IngestError, ingest_file
    from nhdip.data.infer import infer_definition, validate_definition

    from .admin_data import owner_of
    from .db_uploads import auto_target

    if data_origin not in ("actual", "simulated") or origin not in ("bank", "ext"):
        raise HTTPException(422, "origin 은 bank | ext, data_origin 은 actual | simulated")
    owner = owner_of(session, admin, owner_org)
    name, content = await _read(file, "dataset", session, request, admin.emp_no)
    d, matches = auto_target(session, name, content, include_common=True)
    created = False
    if d is None:
        try:
            out = infer_definition(content, name, origin=origin)
        except (IngestError, ValueError) as exc:
            raise HTTPException(422, f"파일에서 정의를 만들 수 없습니다 — {exc}") from exc
        base, n = out["code"], 2
        while session.get(Dataset, out["code"]) is not None:
            out["code"], n = f"{base}_{n}"[:60], n + 1
        fields = ("code", "name", "origin", "kind", "description", "file_pattern", "refresh_cycle", "columns", "key_columns", "as_of_column", "mapping", "quality_rules", "parser")
        defn = {k: out.get(k) for k in fields}
        problems = validate_definition(defn)
        if problems:
            raise HTTPException(422, " · ".join(problems[:6]))
        d = Dataset(**{k: v for k, v in defn.items() if v is not None}, common=bool(common))
        session.add(d)
        session.flush()
        created = True
    elif common and not getattr(d, "common", False):
        raise HTTPException(409, f"이 파일은 부서 자료 '{d.name}' 의 새 판입니다 — 공통 통합 DB 로 옮기려면 [데이터셋·문서]에서 그 정의를 공통으로 바꾸세요")
    if getattr(d, "common", False):
        owner = None  # 공통 통합 DB — 소유 팀 없음
    try:
        v = ingest_file(session, d, name, content, data_origin=data_origin, actor=admin.emp_no, note=note, force=force, owner_org=owner)
    except (IngestError, ValueError) as exc:
        session.rollback()
        raise HTTPException(422, f"올릴 수 없습니다 — {exc}") from exc
    if created and v.status != "committed":
        bad = [f"{c['rule']}: {c['detail']}" for c in (v.quality or {}).get("checks", []) if not c.get("passed") and c.get("severity") == "error"][:5]
        session.rollback()
        raise HTTPException(422, "품질 검사를 통과하지 못해 데이터셋을 만들지 않았습니다 — " + " · ".join(bad))
    if created:
        emit(session, "config.changed", {"kind": "dataset", "code": d.code}, admin.emp_no)
    audit(session, admin.emp_no, "admin.dataset.auto_upload", "dataset", d.code, {"file": name, "created": created, "version": v.version, "status": v.status}, client_ip(request))
    session.commit()
    if created:
        try:
            from nhdip.data.catalog import index_dataset_cards

            index_dataset_cards(session, [d.code])
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
    return {"dataset": d.code, "name": d.name, "created": created, "version": v.version, "id": v.id, "status": v.status, "quality": v.quality, "rows": v.row_count,
            "isCurrent": v.is_current, "matches": matches[:3], "ownerOrg": owner}
