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

from .deps import client_ip, current_user, user_resources

router = APIRouter(prefix="/documents", tags=["documents"])
RESOURCE = "documents"


def _viewer(user: AppUser = Depends(current_user), session: Session = Depends(get_session)) -> AppUser:
    """문서 화면 권한 또는 영업점 공통(연결 근거 문서만 — 문서마다 _check) — 둘 다 아니면 문서를 찾기 전에 막는다."""
    from nhdip.views.plan_share import in_branch_common

    allowed = user_resources(session, user)
    if allowed is not None and RESOURCE not in allowed and not in_branch_common(session, user, allowed):
        raise HTTPException(403, f"이 화면에 대한 권한이 없습니다 ({RESOURCE})")
    return user


def _missing(session: Session, user: AppUser, msg: str) -> HTTPException:
    """문서를 못 찾았을 때 — 문서 화면 권한이 없는 영업점 공통 사용자에게는 '권한 없음' 과 같은 답(연결되지 않은 문서의 존재를 드러내지 않는다)."""
    allowed = user_resources(session, user)
    if allowed is not None and RESOURCE not in allowed:
        return HTTPException(403, f"이 화면에 대한 권한이 없습니다 ({RESOURCE})")
    return HTTPException(404, msg)


def _check(session: Session, user: AppUser, doc) -> None:
    """원본 열람 권한 — 문서 화면 권한 + 문서 등급(부서한정). 문서 화면 권한이 없는 영업점 공통(영업본부 · 영업점) 사용자는
    영업점 참고 수행방안의 연결 근거 문서만 연다(views.plan_share.branch_grant — 지금 원장 기준)."""
    from nhdip.views.plan_share import branch_grant, in_branch_common

    allowed = user_resources(session, user)
    grant = None
    if allowed is not None and (RESOURCE not in allowed or (doc.meta or {}).get("accessClass") == "dept_only") and in_branch_common(session, user, allowed):
        grant = set(branch_grant(session).docs)
    if allowed is not None and RESOURCE not in allowed and doc.doc_code not in (grant or set()):
        raise HTTPException(403, f"이 화면에 대한 권한이 없습니다 ({RESOURCE})")
    ok, why = doc_visible(session, user, doc.doc_code, doc.meta, grant=grant)
    if not ok:
        raise HTTPException(403, why)


@router.get("/view")
def view_document(
    id: str | None = Query(None, max_length=80),
    file: str | None = Query(None, max_length=300),
    title: str | None = Query(None, max_length=300),
    page: int | None = Query(None, ge=1, le=10000),
    q: str | None = Query(None, max_length=2000),
    session: Session = Depends(get_session),
    user: AppUser = Depends(_viewer),
):
    """면별 본문 + 인용 하이라이트. 문서는 id → 파일명 → 제목 순으로 찾는다."""
    if not (id or file or title):
        raise HTTPException(422, "id · file · title 중 하나가 필요합니다")
    hit = viewer.resolve(session, id, file, title)
    if not hit:
        raise _missing(session, user, "등록된 원본 문서가 없습니다")
    origin, doc = hit
    _check(session, user, doc)
    return viewer.view(session, origin, doc, page, q)


@router.get("/{origin}/{doc_id}/file")
def document_file(
    origin: str,
    doc_id: str,
    request: Request,
    session: Session = Depends(get_session),
    user: AppUser = Depends(_viewer),
):
    """원본 파일(업로드본) — 화면에서 바로 열 수 있게 inline 으로 내려준다."""
    if origin not in viewer.ORIGINS:
        raise HTTPException(404, "문서 없음")
    hit = viewer.resolve(session, doc_id=doc_id)
    if not hit or hit[0] != origin:
        raise _missing(session, user, "문서 없음")
    _, doc = hit
    _check(session, user, doc)
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

