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

from .deps import client_ip, require_resource

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/formats")
def formats(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("reports"))):
    """관리자 설정 `report.export_formats` 로 켠 형식 목록."""
    return enabled_formats(session)


@router.get("/{tab_key}/export")
def export_report(
    tab_key: str,
    request: Request,
    format: str = Query("pdf", pattern="^[a-z]{3,4}$"),
    session: Session = Depends(get_session),
    user: AppUser = Depends(require_resource("reports")),
):
    if format not in enabled_formats(session):
        raise HTTPException(422, f"사용하지 않는 형식입니다: {format}")
    row = get_current_row(session, f"report.{tab_key}")
    if not row:
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
