"""관리자 [조직 · 인사 동기화] (Phase R · 가이드 §3) — 조직 · 인사 .dat 업로드, 미리보기(dry-run), 이력, 필터 규칙, SSO 상태.

POST /admin/data-sync/organization · /admin/data-sync/employee  (multipart file, dry_run)
GET  /admin/data-sync                                            현황 · 최근 이력(감사 로그) · 설정 · SSO 검증기 상태
PUT  /admin/data-sync/settings                                   필터 규칙 · 유형 규칙 · SSO 계정 정책
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip import ncsso
from nhdip.config import get_settings
from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser, AuditLog, OrgUnit, Setting
from nhdip.orgsync import DEFAULT_TYPE_RULES, SyncError, filter_rules, sync_employees, sync_organizations

from .admin_data import _read
from .deps import client_ip, require_admin

router = APIRouter(prefix="/admin/data-sync", tags=["admin"], dependencies=[Depends(require_admin)])
SETTING_KEYS = ("sync.filter_rules", "sync.org_type_rules", "sync.overwrite_manual_orgs", "sso.auto_create_user", "sso.reactivate_disabled", "sso.default_org")


def _iso(v: Any) -> str | None:
    return v.isoformat() if v else None


async def _run(kind: str, file: UploadFile, dry_run: bool, request: Request, session: Session, admin: AppUser) -> dict[str, Any]:
    name, content = await _read(file, "hr_sync", session, request, admin.emp_no)
    fn = sync_organizations if kind == "organization" else sync_employees
    try:
        res = fn(session, content, dry_run=dry_run)
    except SyncError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        session.rollback()  # 한 트랜잭션 — 일부만 반영되지 않게 (가이드 문제 6)
        raise
    out = res.json()
    audit(session, admin.emp_no, f"admin.sync.{kind}" + (".dry_run" if dry_run else ""), "data_sync", name[:120],
          {k: v for k, v in out.items() if k not in ("errors", "warnings")} | {"errors": len(res.errors), "warnings": len(res.warnings), "file": name}, client_ip(request))
    session.commit()
    return {"file": name, **out}


@router.post("/organization")
async def sync_org(request: Request, file: UploadFile = File(...), dry_run: bool = Form(False), session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    return await _run("organization", file, dry_run, request, session, admin)


@router.post("/employee")
async def sync_emp(request: Request, file: UploadFile = File(...), dry_run: bool = Form(False), session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    return await _run("employee", file, dry_run, request, session, admin)


@router.get("")
def overview(session: Session = Depends(get_session)):
    st = get_settings()
    org_src = dict(session.execute(select(OrgUnit.source, func.count()).group_by(OrgUnit.source)).all())
    org_active = session.execute(select(func.count()).select_from(OrgUnit).where(OrgUnit.source == "dat", OrgUnit.active)).scalar() or 0
    users = {f"{s}:{status}": n for s, status, n in session.execute(select(AppUser.source, AppUser.status, func.count()).group_by(AppUser.source, AppUser.status)).all()}
    hist = session.execute(select(AuditLog).where(AuditLog.action.like("admin.sync.%")).order_by(AuditLog.id.desc()).limit(20)).scalars().all()
    settings = {k: (s.value if (s := session.get(Setting, k)) is not None else None) for k in SETTING_KEYS}
    try:
        filter_rules(session)
        rules_error = None
    except SyncError as exc:
        rules_error = str(exc)
    return {
        "orgs": {"dat": int(org_src.get("dat", 0)), "datActive": int(org_active), "manual": int(org_src.get("manual", 0))},
        "users": users,
        "history": [{"id": a.id, "at": _iso(a.at), "actor": a.actor, "action": a.action, "file": a.target_id, "detail": a.detail} for a in hist],
        "settings": settings,
        "rulesError": rules_error,
        "defaults": {"orgTypeRules": DEFAULT_TYPE_RULES},
        "sso": {**ncsso.verifier_health(), "label": st.nc_sso_label, "allowedToa": st.nc_sso_allowed_toa, "localLogin": st.nc_sso_local_login, "loginUrl": st.nc_sso_login_url},
    }


class SyncSettingsIn(BaseModel):
    filter_rules: list[dict[str, Any]] | None = None
    org_type_rules: list[dict[str, Any]] | None = None
    overwrite_manual_orgs: bool | None = None
    auto_create_user: bool | None = None
    reactivate_disabled: bool | None = None
    default_org: str | None = None


@router.put("/settings")
def put_settings(body: SyncSettingsIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    import re

    patch = body.model_dump(exclude_unset=True)
    keymap = {"filter_rules": "sync.filter_rules", "org_type_rules": "sync.org_type_rules", "overwrite_manual_orgs": "sync.overwrite_manual_orgs",
              "auto_create_user": "sso.auto_create_user", "reactivate_disabled": "sso.reactivate_disabled", "default_org": "sso.default_org"}
    if "org_type_rules" in patch:
        for r in patch["org_type_rules"] or []:
            try:
                re.compile(str(r.get("pattern")))
            except re.error as exc:
                raise HTTPException(422, f"유형 규칙 정규식 오류: {r.get('pattern')} — {exc}") from exc
            if not r.get("type"):
                raise HTTPException(422, "유형 규칙에 type 이 필요합니다")
    if patch.get("default_org") and session.get(OrgUnit, patch["default_org"]) is None:
        raise HTTPException(422, "기본 소속 조직이 없습니다")
    for k, v in patch.items():
        key = keymap[k]
        s = session.get(Setting, key)
        if s is None:
            s = Setting(key=key, value=v if v is not None else "", description="", updated_by=admin.emp_no)
            session.add(s)
        else:
            s.value, s.updated_by = (v if v is not None else ""), admin.emp_no
    session.flush()
    try:
        filter_rules(session)  # 잘못된 필터는 저장하지 않는다
    except SyncError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    audit(session, admin.emp_no, "admin.sync.settings", "setting", "sync", patch, client_ip(request))
    session.commit()
    return overview(session)
