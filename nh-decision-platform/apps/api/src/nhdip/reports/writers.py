"""요소 목록 → 파일 바이트 (HTML · PDF · HWPX · HWP)."""
from __future__ import annotations

import html
import io
import os
import threading
from typing import Any

from .model import Bullets, Callout, Element, EvidenceList, Heading, KeyValues, Para, Table

CONTENT_TYPES = {
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
    "hwpx": "application/hwp+zip",
    "hwp": "application/x-hwp",
}


# ═════════════════════════ HTML ═════════════════════════
_CSS = """
  :root { color-scheme: light }
  body { font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif;
         max-width: 920px; margin: 40px auto; padding: 0 24px; color: #1c1e21; line-height: 1.6; }
  h1 { font-size: 24px; margin: 0 0 4px }
  h2 { font-size: 18px; margin: 32px 0 8px; padding-bottom: 6px; border-bottom: 1px solid #dee3e9 }
  h3 { font-size: 15px; margin: 20px 0 6px; color: #444950 }
  p, li, td, th { font-size: 13.5px }
  .meta { color: #5d6c7b; font-size: 12px; margin: 0 0 24px; white-space: pre-line }
  .muted { color: #616f7f; font-size: 11.5px }
  .op_title { font-weight: 700; color: #0a1317; margin: 12px 0 4px }
  table { width: 100%; border-collapse: collapse; margin: 12px 0 }
  caption { text-align: left; font-size: 12px; color: #5d6c7b; padding-bottom: 6px }
  th, td { border-bottom: 1px solid #dee3e9; padding: 6px 8px; text-align: left }
  th { background: #f1f4f7; font-weight: 700 }
  td.right, th.right { text-align: right; font-variant-numeric: tabular-nums }
  td.center, th.center { text-align: center }
  tr.hl td { background: rgba(242,169,24,.14); font-weight: 700 }
  .callout { border-radius: 10px; padding: 10px 14px; margin: 12px 0; background: rgba(0,100,224,.05) }
  .callout.attention { background: rgba(242,169,24,.1) }
  .callout.critical { background: rgba(228,30,63,.06) }
  .callout.success { background: rgba(49,162,76,.07) }
  ul.evidence { list-style: none; padding: 0; margin: 8px 0 0 }
  ul.evidence li { border-top: 1px dashed #dee3e9; padding: 6px 0; font-size: 12px }
  .cat { display: inline-block; background: #e9eef4; border-radius: 10px; padding: 1px 8px; font-size: 11px; margin-right: 6px }
  .src, .snippet { display: block; color: #5d6c7b; font-size: 11.5px }
  dl { margin: 12px 0 }
  dl > div { display: flex; gap: 12px; border-bottom: 1px solid #dee3e9; padding: 4px 0 }
  dt { width: 180px; color: #5d6c7b; font-size: 12px }
  dd { margin: 0; font-size: 13px }
"""


def to_html(title: str, els: list[Element]) -> bytes:
    e = html.escape
    out: list[str] = []
    for el in els:
        if isinstance(el, Heading):
            lv = min(max(el.level, 1), 3)
            out.append(f"<h{lv}>{e(el.text)}</h{lv}>")
        elif isinstance(el, Para):
            cls = "" if el.style == "body" else f' class="{el.style}"'
            out.append(f"<p{cls}>{e(el.text)}</p>")
        elif isinstance(el, Bullets):
            tag = "ol" if el.ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{e(i)}</li>" for i in el.items) + f"</{tag}>")
        elif isinstance(el, Callout):
            out.append(f'<div class="callout {e(el.tone)}">{e(el.text)}</div>')
        elif isinstance(el, KeyValues):
            out.append("<dl>" + "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in el.items) + "</dl>")
        elif isinstance(el, Table):
            al = el.aligns or ["left"] * len(el.columns)
            head = "".join(f'<th class="{a}">{e(c)}</th>' for c, a in zip(el.columns, al))
            hl = ' class="hl"'
            body = "".join(
                f"<tr{hl if i in el.highlight else ''}>" + "".join(f'<td class="{a}">{e(v)}</td>' for v, a in zip(r, al)) + "</tr>"
                for i, r in enumerate(el.rows)
            )
            cap = f"<caption>{e(el.caption)}</caption>" if el.caption else ""
            out.append(f"<table>{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            if el.note:
                out.append(f'<p class="muted">{e(el.note)}</p>')
        elif isinstance(el, EvidenceList):
            out.append('<ul class="evidence">' + "".join(
                f'<li><span class="cat">{e(c)}</span> <b>{e(lab)}</b><span class="src">{e(src)}</span>'
                + (f'<span class="snippet">{e(sn)}</span>' if sn else "") + "</li>"
                for c, lab, src, sn in el.items
            ) + "</ul>")
    doc = f'<!doctype html>\n<html lang="ko"><head><meta charset="utf-8" />\n<title>{e(title)}</title>\n<style>{_CSS}</style></head>\n<body>\n' + "\n".join(out) + "\n</body></html>"
    return doc.encode("utf-8")


# ═════════════════════════ PDF (reportlab) ═════════════════════════
def _fonts(font_cfg: dict[str, Any]) -> tuple[str, str]:
    """본문 · 굵은 글꼴 등록. TTF 가 없으면 내장 CID 글꼴(HYGothic-Medium)로 대체."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    regular, bold = font_cfg.get("regular"), font_cfg.get("bold")
    if regular and os.path.exists(regular):
        if "NHReport" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("NHReport", regular))
            pdfmetrics.registerFont(TTFont("NHReport-Bold", bold if bold and os.path.exists(bold) else regular))
        return "NHReport", "NHReport-Bold"
    if "HYGothic-Medium" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium", "HYGothic-Medium"


def to_pdf(title: str, els: list[Element], font_cfg: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer
    from reportlab.platypus import Table as RLTable
    from reportlab.platypus import TableStyle

    font, bold = _fonts(font_cfg)
    st = {
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=18, leading=24, spaceAfter=4),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=13.5, leading=19, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#0a1317")),
        "h3": ParagraphStyle("h3", fontName=bold, fontSize=11.5, leading=16, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#444950")),
        "body": ParagraphStyle("body", fontName=font, fontSize=9.5, leading=14.5, spaceAfter=4, wordWrap="CJK"),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=8.5, leading=12.5, spaceAfter=10, textColor=colors.HexColor("#5d6c7b"), wordWrap="CJK"),
        "muted": ParagraphStyle("muted", fontName=font, fontSize=8, leading=11.5, textColor=colors.HexColor("#616f7f"), wordWrap="CJK"),
        "op_title": ParagraphStyle("op_title", fontName=bold, fontSize=10, leading=14, spaceBefore=6, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=8.5, leading=11.5, wordWrap="CJK"),
        "cell_r": ParagraphStyle("cell_r", fontName=font, fontSize=8.5, leading=11.5, alignment=TA_RIGHT, wordWrap="CJK"),
        "th": ParagraphStyle("th", fontName=bold, fontSize=8.5, leading=11.5, wordWrap="CJK"),
        "th_r": ParagraphStyle("th_r", fontName=bold, fontSize=8.5, leading=11.5, alignment=TA_RIGHT, wordWrap="CJK"),
    }
    tone_bg = {"info": "#eef4fc", "attention": "#fdf3df", "critical": "#fcebee", "success": "#ebf6ee"}

    def p(text: str, style: str = "body") -> Paragraph:
        return Paragraph(html.escape(text).replace("\n", "<br/>"), st[style])

    width = A4[0] - 36 * mm
    story: list[Any] = []
    for el in els:
        if isinstance(el, Heading):
            story.append(p(el.text, f"h{min(max(el.level, 1), 3)}"))
        elif isinstance(el, Para):
            story.append(p(el.text, el.style))
        elif isinstance(el, Bullets):
            story.append(ListFlowable([ListItem(p(i), leftIndent=10) for i in el.items], bulletType="1" if el.ordered else "bullet", start=None if el.ordered else "•", leftIndent=12, bulletFontName=font, bulletFontSize=8))
        elif isinstance(el, Callout):
            t = RLTable([[p(el.text)]], colWidths=[width])
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tone_bg.get(el.tone, "#eef4fc"))), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            story += [Spacer(1, 4), t, Spacer(1, 4)]
        elif isinstance(el, KeyValues):
            t = RLTable([[p(k, "meta"), p(v)] for k, v in el.items], colWidths=[50 * mm, width - 50 * mm])
            t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dee3e9")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(t)
        elif isinstance(el, Table):
            if el.caption:
                story.append(p(el.caption, "meta"))
            al = el.aligns or ["left"] * len(el.columns)
            data = [[p(c, "th_r" if a == "right" else "th") for c, a in zip(el.columns, al)]] + [[p(v, "cell_r" if a == "right" else "cell") for v, a in zip(r, al)] for r in el.rows]
            t = RLTable(data, colWidths=[width / max(len(el.columns), 1)] * len(el.columns), repeatRows=1)
            style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f4f7")), ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dee3e9")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
            style += [("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#fcefd2")) for i in el.highlight]
            t.setStyle(TableStyle(style))
            story += [t, Spacer(1, 4)]
            if el.note:
                story.append(p(el.note, "muted"))
        elif isinstance(el, EvidenceList):
            for c, lab, src, sn in el.items:
                story.append(p(f"[{c}] {lab}", "body"))
                story.append(p(src + (f"\n{sn}" if sn else ""), "muted"))

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.HexColor("#616f7f"))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{title} · {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=title, author="NH AI 경영 의사결정 플랫폼").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ═════════════════════════ HWPX · HWP (python-hwpx) ═════════════════════════
# python-hwpx 저장 단계의 XML 스키마 검증(lxml)이 동시 실행에 안전하지 않아 프로세스 안에서 한 번에 하나만 만든다
# (성능 측정 8.3 에서 동시 4건 요청 시 XMLSchemaParseError 재현)
_HANGUL_LOCK = threading.Lock()


def to_hangul(els: list[Element], fmt: str = "hwpx") -> bytes:
    with _HANGUL_LOCK:
        return _to_hangul(els, fmt)


def _to_hangul(els: list[Element], fmt: str = "hwpx") -> bytes:
    from hwpx import HwpxDocument
    doc = HwpxDocument.new()

    def para(text: str) -> None:
        doc.add_paragraph(text)

    for el in els:
        if isinstance(el, Heading):
            doc.add_heading(el.text, level=min(max(el.level, 1), 3))
        elif isinstance(el, Para):
            for line in el.text.split("\n"):
                para(line)
        elif isinstance(el, Bullets):
            for i, item in enumerate(el.items, start=1):
                para(f"{i}. {item}" if el.ordered else f"• {item}")
        elif isinstance(el, Callout):
            t = doc.add_table(1, 1)
            t.set_cell_text(0, 0, el.text)
        elif isinstance(el, KeyValues):
            t = doc.add_table(len(el.items), 2)
            for r, (k, v) in enumerate(el.items):
                t.set_cell_text(r, 0, k)
                t.set_cell_text(r, 1, v)
        elif isinstance(el, Table):
            if el.caption:
                para(el.caption)
            if not el.columns:
                continue
            t = doc.add_table(len(el.rows) + 1, len(el.columns))
            for c, label in enumerate(el.columns):
                t.set_cell_text(0, c, label)
            for r, row in enumerate(el.rows, start=1):
                for c, v in enumerate(row):
                    t.set_cell_text(r, c, v)
            if el.note:
                para(el.note)
        elif isinstance(el, EvidenceList):
            for c, lab, src, sn in el.items:
                para(f"[{c}] {lab} — {src}" + (f" · {sn}" if sn else ""))
    return doc.to_bytes(format=fmt)
