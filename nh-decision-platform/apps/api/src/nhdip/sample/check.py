"""저장소 사본(sample-data/<기준월>) ↔ 생성기 결과 비교 (RD-02) — 엑셀은 셀 값, CSV 는 글, PDF 는 면별 글로 비교한다.

PDF 바이트는 글꼴(나눔고딕 · 내장 CID)과 환경에 따라 달라 바이트 대신 추출한 글을 본다.
"""
from __future__ import annotations

import io
import json
import os
from typing import Any

from .build import Package


def _cells(content: bytes) -> list[list[Any]]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    return [[list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets]


def _pdf_text(content: bytes) -> list[str]:
    from pypdf import PdfReader

    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(content)).pages]


def same(name: str, a: bytes, b: bytes) -> bool:
    low = name.lower()
    if low.endswith(".xlsx"):
        return _cells(a) == _cells(b)
    if low.endswith(".pdf"):
        return _pdf_text(a) == _pdf_text(b)
    return a == b


def compare_dir(pkg: Package, folder: str) -> list[str]:
    diffs: list[str] = []
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as fh:
            man = json.load(fh)
    except OSError:
        return [f"manifest.json 없음: {folder}"]
    want = {f["name"] for f in man.get("files", [])}
    have = {f.name for f in pkg.files}
    diffs += [f"사본에만 있음: {n}" for n in sorted(want - have)]
    diffs += [f"생성기에만 있음: {n}" for n in sorted(have - want)]
    for f in pkg.files:
        path = os.path.join(folder, "datasets" if f.kind == "dataset" else "documents", f.name)
        if not os.path.exists(path):
            diffs.append(f"파일 없음: {path}")
            continue
        with open(path, "rb") as fh:
            if not same(f.name, f.content, fh.read()):
                diffs.append(f"내용 다름: {f.name}")
    return diffs
