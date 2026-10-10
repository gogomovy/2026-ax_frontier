"""보고서 서버 변환 (F.17 · MDL-14) — 화면 산출물 `report.{tab_key}` → HTML · PDF · HWPX · HWP."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from nhdip.models import Setting
from nhdip.views.cascade import DEFAULT_UNIT_LABELS

from .model import build
from .writers import CONTENT_TYPES, to_hangul, to_html, to_pdf

DEFAULT_FORMATS = ["pdf", "hwpx", "hwp", "html"]
DEFAULT_FONTS = {"regular": "/usr/share/fonts/truetype/nanum/NanumGothic.ttf", "bold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"}


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s and s.value is not None else default


def enabled_formats(session: Session) -> list[str]:
    return [f for f in _setting(session, "report.export_formats", DEFAULT_FORMATS) if f in CONTENT_TYPES]


def file_name(report: dict[str, Any], fmt: str) -> str:
    return f"{str(report.get('asOf', '')).replace('-', '')}_{report.get('kind', 'report')}_보고서.{fmt}"


def render(report: dict[str, Any], fmt: str, units: dict[str, str] | None = None, fonts: dict[str, Any] | None = None) -> bytes:
    els = build(report, units or DEFAULT_UNIT_LABELS)
    title = report.get("title", "보고서")
    if fmt == "html":
        return to_html(title, els)
    if fmt == "pdf":
        return to_pdf(title, els, fonts or DEFAULT_FONTS)
    if fmt in ("hwpx", "hwp"):
        return to_hangul(els, fmt)
    raise ValueError(f"지원하지 않는 형식: {fmt}")


def export(session: Session, report: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
    data = render(report, fmt, _setting(session, "format.unit_labels", DEFAULT_UNIT_LABELS), _setting(session, "report.pdf_fonts", DEFAULT_FONTS))
    return data, file_name(report, fmt), CONTENT_TYPES[fmt]
