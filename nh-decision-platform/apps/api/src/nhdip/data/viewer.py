"""원본 문서 뷰어 (F.12 · DB-07) — 면별 본문 + 근거 인용 위치 하이라이트.

면 본문 우선순위
  1) 원본 PDF 파일(파일 저장소)  → 면별 텍스트 추출          source = "file"
  2) 문서 메타 `pages`(시드 발췌) → 근거 인용이 실린 면만     source = "excerpt"
  3) 청크(page · seq 순)          → 텍스트 업로드 문서        source = "chunks"
"""
from __future__ import annotations

import io
import os
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.models import source

ORIGINS = ("bank", "ext")
_SPLIT = re.compile(r"[.。!?…·,;:\n()\[\]“”\"']+")
MIN_FRAGMENT = 8


def resolve(session: Session, doc_id: str | None = None, file_name: str | None = None, title: str | None = None) -> tuple[str, Any] | None:
    """문서 코드 → 파일명 → 제목 순으로 현재 버전 문서를 찾는다."""
    for origin in ORIGINS:
        t = source(origin)
        base = select(t.document).where(t.document.is_current)
        for cond in (
            t.document.doc_code == doc_id if doc_id else None,
            t.document.file_name == file_name if file_name else None,
            t.document.meta["fileName"].astext == file_name if file_name else None,
            t.document.title == title if title else None,
        ):
            if cond is None:
                continue
            d = session.execute(base.where(cond).limit(1)).scalar()
            if d:
                return origin, d
    return None


def safe_file_path(doc: Any) -> str | None:
    """파일 저장소 안의 실제 파일만 허용 (경로 이탈 차단)."""
    p = doc.file_path
    if not p:
        return None
    root = os.path.realpath(get_settings().filestore_dir)
    real = os.path.realpath(p)
    if not real.startswith(root + os.sep) or not os.path.isfile(real):
        return None
    return real


def page_texts(session: Session, origin: str, doc: Any) -> tuple[str, list[dict[str, Any]]]:
    path = safe_file_path(doc)
    if path and (doc.mime == "application/pdf" or path.lower().endswith(".pdf")):
        try:
            from pypdf import PdfReader

            with open(path, "rb") as fh:
                reader = PdfReader(io.BytesIO(fh.read()))
            pages = [{"page": i + 1, "text": (p.extract_text() or "").strip()} for i, p in enumerate(reader.pages)]
            if any(p["text"] for p in pages):
                return "file", pages
        except Exception:  # noqa: BLE001 — 손상 파일은 청크로 대체
            pass
    meta_pages = (doc.meta or {}).get("pages")
    if meta_pages:
        return "excerpt", [{"page": int(p["page"]), "text": p.get("text", ""), "section": p.get("section")} for p in meta_pages]
    t = source(origin)
    rows = session.execute(select(t.chunk.page, t.chunk.text).where(t.chunk.document_id == doc.id).order_by(t.chunk.page, t.chunk.seq)).all()
    by: dict[int, list[str]] = {}
    for page, text in rows:
        by.setdefault(page or 1, []).append(text)
    return "chunks", [{"page": p, "text": "\n\n".join(v)} for p, v in sorted(by.items())]


def _normalize(s: str) -> tuple[str, list[int]]:
    """공백을 한 칸으로 모은 문자열과, 각 글자의 원문 위치."""
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(s):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch)
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def _find_all(hay: str, needle: str) -> list[int]:
    out, start = [], 0
    while needle:
        i = hay.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + len(needle)
    return out


def highlights(text: str, query: str | None) -> list[dict[str, int]]:
    """인용문 전체가 있으면 그 범위, 없으면 8자 이상 조각들의 위치 (원문 기준 [start, end))."""
    if not query or not query.strip() or not text:
        return []
    norm, idx = _normalize(text)
    q, _ = _normalize(query.strip())
    spans: list[tuple[int, int]] = []
    hits = _find_all(norm, q)
    if hits:
        spans = [(h, h + len(q)) for h in hits]
    else:
        for frag in {f.strip() for f in _SPLIT.split(q)}:
            if len(frag) < MIN_FRAGMENT:
                continue
            spans += [(h, h + len(frag)) for h in _find_all(norm, frag)]
    merged: list[list[int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [{"start": idx[s], "end": idx[e - 1] + 1} for s, e in merged]


def view(session: Session, origin: str, doc: Any, page: int | None = None, query: str | None = None) -> dict[str, Any]:
    src, pages = page_texts(session, origin, doc)
    total_hl = 0
    for p in pages:
        p["highlights"] = highlights(p["text"], query)
        total_hl += len(p["highlights"])
    nums = [p["page"] for p in pages]
    focus = page if page in nums else None
    hit_pages = [p["page"] for p in pages if p["highlights"]]
    if hit_pages and (focus is None or focus not in hit_pages):
        # 지정한 면에 인용이 없으면 인용이 있는 가장 가까운 면
        focus = min(hit_pages, key=lambda n: abs(n - (page or n)))
    if focus is None and nums:
        focus = nums[0]
    m = doc.meta or {}
    return {
        "docId": doc.doc_code,
        "origin": origin,
        "version": doc.version,
        "title": doc.title,
        "issuer": doc.issuer or m.get("issuer"),
        "effectiveDate": doc.published_at.isoformat() if doc.published_at else m.get("effectiveDate"),
        "dbClass": doc.doc_class,
        "fileName": doc.file_name or m.get("fileName"),
        "pageCount": m.get("pageCount") or (max(nums) if nums else 0),
        "hasFile": safe_file_path(doc) is not None,
        "source": src,
        "requestedPage": page,
        "focusPage": focus,
        "query": query,
        "matched": total_hl > 0,
        "pages": pages,
    }
