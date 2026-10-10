"""원본 문서 뷰어 API (F.12 · DB-07)."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from nhdip.data import viewer
from nhdip.db import get_session
from nhdip.events import audit
from nhdip.graph.evidence import doc_visible
from nhdip.models import AppUser

from .deps import client_ip, require_resource

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/view")
def view_document(
    id: str | None = Query(None, max_length=80),
    file: str | None = Query(None, max_length=300),
    title: str | None = Query(None, max_length=300),
    page: int | None = Query(None, ge=1, le=10000),
    q: str | None = Query(None, max_length=2000),
    session: Session = Depends(get_session),
    user: AppUser = Depends(require_resource("documents")),
):
    """면별 본문 + 인용 하이라이트. 문서는 id → 파일명 → 제목 순으로 찾는다."""
    if not (id or file or title):
        raise HTTPException(422, "id · file · title 중 하나가 필요합니다")
    hit = viewer.resolve(session, id, file, title)
    if not hit:
        raise HTTPException(404, "등록된 원본 문서가 없습니다")
    origin, doc = hit
    ok, why = doc_visible(session, user, doc.doc_code, doc.meta)
    if not ok:
        raise HTTPException(403, why)
    return viewer.view(session, origin, doc, page, q)


@router.get("/{origin}/{doc_id}/file")
def document_file(
    origin: str,
    doc_id: str,
    request: Request,
    session: Session = Depends(get_session),
    user: AppUser = Depends(require_resource("documents")),
):
    """원본 파일(업로드본) — 화면에서 바로 열 수 있게 inline 으로 내려준다."""
    if origin not in viewer.ORIGINS:
        raise HTTPException(404, "문서 없음")
    hit = viewer.resolve(session, doc_id=doc_id)
    if not hit or hit[0] != origin:
        raise HTTPException(404, "문서 없음")
    _, doc = hit
    ok, why = doc_visible(session, user, doc.doc_code, doc.meta)
    if not ok:
        raise HTTPException(403, why)
    path = viewer.safe_file_path(doc)
    if not path:
        raise HTTPException(404, "원본 파일이 저장되어 있지 않습니다")
    audit(session, user.emp_no, "document.open", "document", doc_id, {"origin": origin, "version": doc.version}, client_ip(request))
    session.commit()
    name = doc.file_name or f"{doc_id}"
    return FileResponse(
        path,
        media_type=doc.mime or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )

