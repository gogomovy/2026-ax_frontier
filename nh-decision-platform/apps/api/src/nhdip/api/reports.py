"""보고서 내려받기 API (F.17 · MDL-14) — `GET /reports/{tab_key}/export?format=pdf`."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit
from nhdip.models import AppUser
from nhdip.reports import enabled_formats, export
from nhdip.views.store import get_current_row

from .deps import client_ip, current_user, user_resources

router = APIRouter(prefix="/reports", tags=["reports"])


def _allowed(session: Session, user: AppUser, *resources: str) -> bool:
    allowed = user_resources(session, user)
    return allowed is None or any(r in allowed for r in resources)


@router.get("/formats")
def formats(session: Session = Depends(get_session), user: AppUser = Depends(current_user)):
    """관리자 설정 `report.export_formats` 로 켠 형식 목록 (부서 보고서 · 영업점 보고서 공용)."""
    if not _allowed(session, user, "reports", "branch_reports"):
        raise HTTPException(403, "이 화면에 대한 권한이 없습니다 (reports)")
    return enabled_formats(session)


@router.get("/{tab_key}/export")
def export_report(
    tab_key: str,
    request: Request,
    format: str = Query("pdf", pattern="^[a-z]{3,4}$"),
    office: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]{1,20}$"),
    session: Session = Depends(get_session),
    user: AppUser = Depends(current_user),
):
    # 영업점 보고서(report.branch-*)는 branch_reports 권한 + 영업점 열람 범위(Q44), 그 외는 reports 권한
    branch = tab_key.startswith("branch-")
    if not _allowed(session, user, "branch_reports" if branch else "reports"):
        raise HTTPException(403, f"이 화면에 대한 권한이 없습니다 ({'branch_reports' if branch else 'reports'})")
    if format not in enabled_formats(session):
        raise HTTPException(422, f"사용하지 않는 형식입니다: {format}")
    key, target = f"report.{tab_key}", None
    if branch:
        # 다지점(B.47) — 볼 지점의 범위 산출물(기본 지점은 기존 키)
        from nhdip.scopes import office_scope, resolve_office, scoped_key

        from nhdip.orgs import can_view_office as _can_view

        target = resolve_office(session, user, office)
        if office and not _can_view(session, user, office):
            audit(session, user.emp_no, "branch.office_denied", "office", office, {"artifact": key, "format": format}, client_ip(request))
            session.commit()
            raise HTTPException(404, "보고서 없음")
        key = scoped_key(key, target, office_scope(session)[0])
    row = get_current_row(session, key)
    if not row:
        raise HTTPException(404, "보고서 없음")
    if branch:
        from nhdip.orgs import can_view_office

        code = ((row.payload or {}).get("office") or {}).get("code")
        if not code or (target and str(code) != str(target)) or not can_view_office(session, user, code):
            raise HTTPException(404, "보고서 없음")
    data, name, ctype = export(session, row.payload, format)
    audit(session, user.emp_no, "report.export", "report", tab_key, {"format": format, "generation": row.generation, "bytes": len(data)}, client_ip(request))
    session.commit()
    ascii_name = name.encode("ascii", "ignore").decode() or f"report.{format}"
    return Response(
        content=data,
        media_type=ctype,
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"},
    )
