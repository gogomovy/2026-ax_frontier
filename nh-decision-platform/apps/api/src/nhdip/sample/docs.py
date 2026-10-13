"""시연 문서 PDF (Phase I · 설계 §25.2) — 문서 목록(documents.json) + 화면 근거가 인용한 면 · 절 · 인용문.

- 1면: 표지(제목 · 발행처 · 시행일 · 분류 · 주제어 · 시연용 표기)
- 인용된 면: 절 제목 + 인용문(화면 근거와 같은 글 — 문서 뷰어가 그 면을 열어 강조)
- 인용 없는 면은 비운다(글이 없어 검색 청크가 생기지 않는다). 면 수 = 문서 정의의 면 수
- 글꼴: 보고서 내보내기와 같은 규칙(나눔고딕, 없으면 내장 CID 글꼴) · 같은 입력이면 같은 글(invariant)
"""
from __future__ import annotations

import glob
import io
import json
import os
from typing import Any

HERE = os.path.dirname(__file__)
NOTICE = "※ 시연용 가상 문서 — 실제 기관 문서가 아닙니다. 화면 근거로 인용된 면만 내용을 싣고 나머지 면은 비워 두었습니다."


def catalog() -> list[dict[str, Any]]:
    with open(os.path.join(HERE, "documents.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _screens_dir() -> str:
    from nhdip.seed.run import _screens_dir as d

    return d()


def collect_snippets() -> dict[str, list[dict[str, Any]]]:
    """화면 틀의 문서 근거(doc + snippet)를 문서 제목별로 — 같은 (제목, 인용문)은 한 번."""
    out: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for path in sorted(glob.glob(os.path.join(_screens_dir(), "*.json"))):
        with open(path, encoding="utf-8") as fh:
            stack = [json.load(fh)]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                d = o.get("doc")
                if isinstance(d, dict) and o.get("snippet") and d.get("title"):
                    key = (d["title"], o["snippet"])
                    if key not in seen:
                        seen.add(key)
                        out.setdefault(d["title"], []).append({"snippet": o["snippet"], "sectionPath": d.get("sectionPath"), "page": int(d.get("page") or 1)})
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    for v in out.values():
        v.sort(key=lambda x: (x["page"], x.get("sectionPath") or "", x["snippet"]))
    return out


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pdf(doc: dict[str, Any], snippets: list[dict[str, Any]]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    from nhdip.reports import DEFAULT_FONTS
    from nhdip.reports.writers import _fonts

    font, bold = _fonts(DEFAULT_FONTS)
    T = ParagraphStyle("t", fontName=bold, fontSize=17, leading=25, spaceAfter=12)
    M = ParagraphStyle("m", fontName=font, fontSize=10, leading=16)
    S = ParagraphStyle("s", fontName=font, fontSize=8.5, leading=13, textColor="#666666")
    H = ParagraphStyle("h", fontName=bold, fontSize=12, leading=18, spaceBefore=6, spaceAfter=4)
    P = ParagraphStyle("p", fontName=font, fontSize=10.5, leading=17, spaceAfter=6)
    by: dict[int, list[dict[str, Any]]] = {}
    for sn in snippets:
        by.setdefault(int(sn["page"]), []).append(sn)
    n_pages = max(int(doc.get("pageCount") or 1), max(by, default=1))

    def body(page: int) -> list[Any]:
        out: list[Any] = []
        last_sec = None
        for sn in by.get(page, []):
            sec = sn.get("sectionPath")
            if sec and sec != last_sec:
                out.append(Paragraph(_esc(sec), H))
                last_sec = sec
            out.append(Paragraph(_esc(sn["snippet"]), P))
        return out

    story: list[Any] = [
        Paragraph(_esc(doc["title"]), T),
        Paragraph(_esc(f"발행: {doc.get('issuer') or '-'} · 시행일 {doc.get('effectiveDate') or '-'} · 분류 {doc.get('dbClassLabel') or doc.get('dbClass')}"), M),
        Paragraph(_esc(f"문서 유형: {doc.get('docType') or '-'}"), M),
        Paragraph(_esc("주제어: " + ", ".join(doc.get("tags") or [])), M),
        Spacer(1, 6 * mm),
        Paragraph(_esc(NOTICE), S),
        Spacer(1, 8 * mm),
        *body(1),
    ]
    for page in range(2, n_pages + 1):
        story.append(PageBreak())
        content = body(page)
        story.extend(content or [Spacer(1, 1)])
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=doc["title"], author=doc.get("issuer") or "", subject="시연용 가상 문서", creator="NH 경영 의사결정 플랫폼 · 시연 자료 생성기",
                      leftMargin=22 * mm, rightMargin=22 * mm, topMargin=24 * mm, bottomMargin=22 * mm, invariant=1).build(story)
    return buf.getvalue()


def upload_meta(doc: dict[str, Any]) -> dict[str, Any]:
    """문서 업로드 폼 메타(허용 키만 — 서버 clean_doc_meta 와 같은 키)."""
    keys = ("docType", "isOfficial", "accessClass", "domainLabels", "tags", "effectiveDate", "dbClassLabel")
    return {k: doc[k] for k in keys if doc.get(k) not in (None, "", [])}
