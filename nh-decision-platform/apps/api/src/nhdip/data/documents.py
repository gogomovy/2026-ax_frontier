"""문서 적재 — 텍스트 추출 · 청크 분할 · 버전 · 이벤트 (ONT-04, ING-02).

임베딩과 LLM 구조화는 워커(wf_graph_projection)가 비동기로 수행한다.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.events import audit, emit
from nhdip.models import source


class DocumentError(ValueError):
    pass


def extract_text(filename: str, content: bytes) -> tuple[str, list[tuple[int, str]]]:
    """(전체 텍스트, [(page, text)])"""
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
        return "\n\n".join(t for _, t in pages), pages
    if name.endswith((".hwpx", ".hwp")):
        # 한글 문서(HWPX · HWP 5.0) — 면 정보가 없어 본문 전체를 1면으로, 문단 구분은 빈 줄로 보존
        from hwpx import HwpxDocument

        try:
            text = HwpxDocument.open(io.BytesIO(content)).export_text()
        except Exception as exc:  # noqa: BLE001 — 암호 · 배포용 · 손상 문서
            raise DocumentError(f"한글 문서를 읽지 못했습니다(암호 · 배포용 문서는 해제 후 업로드): {type(exc).__name__}") from exc
        text = "\n\n".join(line.strip() for line in text.splitlines() if line.strip())
        return text, [(1, text)]
    if name.endswith(".docx"):
        text = _docx_text(content)
        return text, [(1, text)]
    if name.endswith((".txt", ".md", ".csv", ".json", ".html")):
        if name.endswith(".md"):
            from .mdtable import decode as md_decode

            text = md_decode(content)  # UTF-8 → CP949 (Phase Q · MD-05)
        else:
            text = content.decode("utf-8-sig", errors="replace")
        if name.endswith(".html"):
            text = re.sub(r"<[^>]+>", " ", text)
        return text, [(1, text)]
    raise DocumentError("지원 형식: .pdf · .docx · .hwpx · .hwp · .txt · .md · .html")


_W_PARA = re.compile(rb"<w:p[\s>].*?</w:p>|<w:p/>", re.S)
_W_RUN = re.compile(rb"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:(tab|br|cr)\b[^>]*/>", re.S)


def _docx_text(content: bytes) -> str:
    """워드(docx) 본문 — word/document.xml 의 문단(w:p)마다 글자(w:t)를 잇는다. 표 칸의 문단도 같은 순서로 읽는다.
    면 정보가 없어 1면으로(한글 문서와 같음). XML 파서 대신 정해진 태그만 읽어 외부 개체 · 개체 확장을 따르지 않는다."""
    import html
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise DocumentError("워드(docx) 문서를 읽지 못했습니다(암호 · 손상 문서는 해제 · 다시 저장 후 업로드)") from exc
    paras = []
    for p in _W_PARA.finditer(xml):
        parts = []
        for m in _W_RUN.finditer(p.group(0)):
            if m.group(1) is not None:
                parts.append(html.unescape(m.group(1).decode("utf-8", errors="replace")))
            else:
                parts.append("\t" if m.group(2) == b"tab" else "\n")
        line = "".join(parts).strip()
        if line:
            paras.append(line)
    return "\n\n".join(paras)


# 문서 구조(작업 3.2.3) — 행정 · 보고 문서의 제목 번호 체계. (수준, 정규식)
HEADINGS: list[tuple[int, re.Pattern[str]]] = [
    (1, re.compile(r"^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]|[IVX]{1,4})\.\s*\S")),
    (1, re.compile(r"^(?:\(?붙임\)?|별첨|첨부)\s*\S")),
    (2, re.compile(r"^\d{1,2}\.(?:\s+|(?=[가-힣A-Za-z]))\S")),
    (3, re.compile(r"^[가-하]\.\s*\S")),
    (4, re.compile(r"^(?:\d{1,2}\)|\([가-하0-9]{1,2}\))\s*\S")),
    (5, re.compile(r"^[□■]\s*\S")),
]


def heading_level(line: str) -> int | None:
    t = line.strip()
    if not t or len(t) > 80 or t.startswith("※"):
        return None
    for lv, pat in HEADINGS:
        if pat.match(t):
            return lv
    return None


class SectionTracker:
    """제목 줄을 만나면 수준별 경로를 갱신. 청크 경로 = 청크 앞부분 제목까지 반영한 경로."""

    def __init__(self) -> None:
        self.stack: list[tuple[int, str]] = []

    def feed(self, line: str) -> bool:
        lv = heading_level(line)
        if lv is None:
            return False
        while self.stack and self.stack[-1][0] >= lv:
            self.stack.pop()
        self.stack.append((lv, line.strip()[:60]))
        return True

    @property
    def path(self) -> str | None:
        return " > ".join(t for _, t in self.stack) or None

    def chunk_path(self, chunk: str) -> str | None:
        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        i = 0
        while i < len(lines) and self.feed(lines[i]):  # 앞부분 제목
            i += 1
        path = self.path
        for ln in lines[i:]:  # 본문 중간 제목은 다음 청크부터
            self.feed(ln)
        return path


def section_paths(chunks: list[str]) -> list[str | None]:
    tr = SectionTracker()
    return [tr.chunk_path(c) for c in chunks]


# 문서 업로드 메타(RD-08) — 허용 키만 저장한다. 값 형식이 틀리면 거절
DOC_META_KEYS: dict[str, type] = {
    "docType": str, "isOfficial": bool, "accessClass": str, "domainLabels": list, "tags": list,
    "effectiveDate": str, "dbClassLabel": str, "pageCount": int,
}
ACCESS_CLASSES = ("public", "internal", "dept_only")


def clean_doc_meta(raw: dict[str, Any] | None, origin: str) -> dict[str, Any]:
    """업로드 폼의 문서 메타 → 저장할 메타. 모르는 키는 버리고, 형식이 틀리면 DocumentError."""
    out: dict[str, Any] = {"docType": "업로드 문서", "isOfficial": origin == "ext"}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        raise DocumentError("문서 메타는 JSON 객체여야 합니다")
    for k, typ in DOC_META_KEYS.items():
        v = raw.get(k)
        if v is None or v == "":
            continue
        if typ is list:
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise DocumentError(f"문서 메타 {k} 는 문자열 목록이어야 합니다")
            v = [x.strip()[:40] for x in v if x.strip()][:20]
        elif typ is bool:
            if not isinstance(v, bool):
                raise DocumentError(f"문서 메타 {k} 는 true/false 여야 합니다")
        elif typ is int:
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 10_000:
                raise DocumentError(f"문서 메타 {k} 는 1~10000 정수여야 합니다")
        else:
            if not isinstance(v, str):
                raise DocumentError(f"문서 메타 {k} 는 문자열이어야 합니다")
            v = v.strip()[:120]
        out[k] = v
    if out.get("accessClass") not in (None, *ACCESS_CLASSES):
        raise DocumentError(f"열람 등급(accessClass)은 {' · '.join(ACCESS_CLASSES)} 중 하나")
    if out.get("effectiveDate"):
        try:
            date.fromisoformat(out["effectiveDate"][:10])
        except ValueError as exc:
            raise DocumentError("시행일(effectiveDate)은 YYYY-MM-DD") from exc
        out["effectiveDate"] = out["effectiveDate"][:10]
    return out


def chunk_text(pages: list[tuple[int, str]], size: int = 700, overlap: int = 100) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for page, text in pages:
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        buf = ""
        for p in paras:
            if len(buf) + len(p) + 1 <= size:
                buf = f"{buf}\n{p}".strip()
                continue
            if buf:
                out.append((page, buf))
            while len(p) > size:
                out.append((page, p[:size]))
                p = p[size - overlap :]
            buf = p
        if buf:
            out.append((page, buf))
    return out


def ingest_document(
    session: Session,
    *,
    origin: str,
    doc_code: str,
    title: str,
    doc_class: str,
    text: str | None = None,
    pages: list[tuple[int, str]] | None = None,
    filename: str | None = None,
    content: bytes | None = None,
    issuer: str | None = None,
    published_at: str | None = None,
    meta: dict[str, Any] | None = None,
    actor: str | None = None,
    emit_event: bool = True,
    owner_org: str | None = None,
):
    """문서 적재 — owner_org = 자료 소유 조직(올린 팀 · 영업점, 없으면 전행 공통). 공통 통합 DB 문서 분류면 소유 팀 없이(§38 CMN)."""
    from nhdip.common_db import is_common_doc_class

    if is_common_doc_class(session, doc_class):
        owner_org = None
    t = source(origin)
    sha = path = mime = None
    meta = dict(meta or {})
    if content is not None and filename:
        text, pages = extract_text(filename, content)
        meta.setdefault("pageCount", len(pages))  # 원본 면 수 (청크 수가 아니라)
        sha = hashlib.sha256(content).hexdigest()
        low = filename.lower()
        mime = ("application/pdf" if low.endswith(".pdf") else "application/hwp+zip" if low.endswith(".hwpx") else "application/x-hwp" if low.endswith(".hwp")
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if low.endswith(".docx") else "text/plain")
        base = os.path.join(get_settings().filestore_dir, origin, "documents")
        try:
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, f"{sha[:16]}_{os.path.basename(filename)}")
            with open(path, "wb") as fh:
                fh.write(content)
        except OSError:
            path = None
    elif not pages:
        # 면 정보가 없는 본문은 1면으로 (면 정보가 있으면 청크에 면 번호를 남긴다)
        pages = [(1, text or "")]
    if not (text or "").strip():
        raise DocumentError("본문 텍스트가 비어 있습니다(스캔 PDF 는 OCR 후 업로드)")
    last = session.execute(select(t.document.version).where(t.document.doc_code == doc_code).order_by(t.document.version.desc()).limit(1)).scalar()
    # 밀려나는 현재 판의 소유 팀 — 소유가 바뀌면(다른 팀이 같은 문서를 다시 올림) 이전 소유 팀 흐름도 다시 돌게
    prev_owners = set(session.execute(select(t.document.owner_org).where(t.document.doc_code == doc_code, t.document.is_current).distinct()).scalars())
    session.execute(update(t.document).where(t.document.doc_code == doc_code).values(is_current=False))
    doc = t.document(
        doc_code=doc_code,
        version=(last or 0) + 1,
        is_current=True,
        title=title,
        doc_class=doc_class,
        issuer=issuer,
        published_at=date.fromisoformat(published_at) if published_at else None,
        file_name=filename,
        file_sha256=sha,
        file_path=path,
        mime=mime,
        text=text or "",
        meta=meta,
        status="ingested",
        uploaded_by=actor,
        owner_org=owner_org,
    )
    session.add(doc)
    session.flush()
    chunks = chunk_text(pages)
    for seq, ((page, chunk), sec) in enumerate(zip(chunks, section_paths([c for _, c in chunks])), start=1):
        session.add(t.chunk(document_id=doc.id, seq=seq, page=page, text=chunk, section_path=sec[:500] if sec else None))
    if emit_event:
        # 소유 조직 · 공통 여부(Phase P · AGW-04 · TDB-07) — 디스패처가 팀 · 공통 조건 흐름(분석 에이전트)을 깨운다
        moved = prev_owners - {owner_org}
        emit(session, "document.ingested", {"origin": origin, "document_id": doc.id, "doc_code": doc_code, "doc_class": doc_class, **({"owner_org": owner_org} if owner_org else {}),
                                            **({"owner_orgs": sorted(o for o in moved if o), "owner_changed": True} if moved else {}),
                                            **({"common": True} if is_common_doc_class(session, doc_class) else {})}, actor)
    audit(session, actor, "document.upload", "document", doc_code, {"origin": origin, "version": doc.version, "doc_class": doc_class})
    return doc


def change_document_owner(session: Session, origin: str, document_id: int, owner_org: str | None, actor: str) -> dict[str, Any] | None:
    """올린 문서의 소유 조직을 바꾼다(관리자) — 이벤트(document.owner_changed)에 이전 · 새 소유를 실어 이전 · 새 소유 팀 흐름과
    그 문서 분류를 근거로 읽는 흐름이 다시 돌게 한다(근거 소유 검사가 바뀐 소유로). 공통 통합 DB 문서 분류는 소유 팀이 없다. 바뀐 것이 없으면 None."""
    from nhdip.common_db import is_common_doc_class

    t = source(origin)
    d = session.get(t.document, document_id)
    if d is None or d.status == "deleted":
        raise DocumentError("바꿀 수 있는 문서가 아닙니다")
    if is_common_doc_class(session, d.doc_class):
        raise DocumentError("공통 통합 DB 문서는 소유 팀 없이 전행 공통입니다")
    old = d.owner_org
    if old == owner_org:
        return None
    d.owner_org = owner_org
    if d.is_current:
        emit(session, "document.owner_changed", {"origin": origin, "document_id": d.id, "doc_code": d.doc_code, "doc_class": d.doc_class, **({"owner_org": owner_org} if owner_org else {}),
                                                 "owner_orgs": sorted(o for o in {old} if o), "owner_changed": True}, actor)
    audit(session, actor, "document.owner_change", "document", d.doc_code, {"origin": origin, "version": d.version, "from": old, "to": owner_org})
    return {"from": old, "to": owner_org, "event": bool(d.is_current)}
