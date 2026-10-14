"""개체 해소 — 미해석 후보 → 별칭 제안 (Phase M · ONB-07 · 결정론 단계)

후보: 문서 추출의 `Candidate` 개체(원래 클래스 · 원문 이름)와 [추출 검토]의 미해석 항목(open).
상대: 별칭 사전의 대표 키 · 별칭, 원천(backing) 객체의 키 · 제목.
점수: 정규화(NFKC · 소문자 · 공백 · 기호 제거) 일치 1.0 → 한쪽이 다른 쪽을 포함(2자 이상) 0.85~1.0 → 그 외 편집 유사도(difflib).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import ExtractionIssue, source

_STRIP = re.compile(r"[\s\-_·•ㆍ.,/()\[\]{}'\"“”‘’:;!?~]+")


def norm(s: Any) -> str:
    return _STRIP.sub("", unicodedata.normalize("NFKC", str(s or "")).lower())


def similarity(a: str, b: str) -> float:
    x, y = norm(a), norm(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    if len(short) >= 2 and short in long_:
        return round(0.85 + 0.15 * len(short) / len(long_), 4)
    return round(difflib.SequenceMatcher(None, x, y).ratio(), 4)


def gather_candidates(session: Session, limit: int = 300) -> list[dict[str, Any]]:
    """{label, raw, count, docs[]} — 같은 (클래스, 정규화 이름)은 하나로."""
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(label: str, raw: str, doc: str | None) -> None:
        if not label or not raw or len(norm(raw)) < 2:
            return
        k = (label, norm(raw))
        e = found.setdefault(k, {"label": label, "raw": raw[:120], "count": 0, "docs": []})
        e["count"] += 1
        if doc and doc not in e["docs"] and len(e["docs"]) < 5:
            e["docs"].append(doc)

    for origin in ("bank", "ext"):
        t = source(origin)
        for d in session.execute(select(t.document).where(t.document.is_current)).scalars():
            for e in (d.extraction or {}).get("entities") or []:
                if e.get("label") == "Candidate":
                    props = e.get("props") if isinstance(e.get("props"), dict) else {}
                    add(str(props.get("raw_label") or ""), str(e.get("name") or ""), d.title)
    for i in session.execute(select(ExtractionIssue).where(ExtractionIssue.status == "open", ExtractionIssue.kind == "unresolved_entity").order_by(ExtractionIssue.id.desc()).limit(limit)).scalars():
        raw = i.raw if isinstance(i.raw, dict) else {}
        if raw.get("label"):
            add(str(raw.get("label")), str(raw.get("key") or raw.get("name") or ""), None)
    return sorted(found.values(), key=lambda e: -e["count"])[:limit]


def universe(schema: Any, rows_by_ds: dict[str, list[dict[str, Any]]]) -> dict[str, list[tuple[str, str]]]:
    """{클래스: [(대표 키, 비교할 이름)]} — 별칭 사전 + 원천 객체 키 · 제목."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for label, entries in (schema.aliases or {}).items():
        for key, aliases in (entries or {}).items():
            out[label].append((key, key))
            out[label] += [(key, a) for a in aliases or []]
    for c in schema.classes or []:
        for bk in c.get("backing") or []:
            for r in rows_by_ds.get(bk.get("dataset"), [])[:5000]:
                k = r.get(bk.get("key_col"))
                if k in (None, ""):
                    continue
                out[c["label"]].append((str(k), str(k)))
                t = r.get(bk.get("title_col")) if bk.get("title_col") else None
                if t not in (None, ""):
                    out[c["label"]].append((str(k), str(t)))
    return out


def best_match(cand: dict[str, Any], uni: dict[str, list[tuple[str, str]]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for key, name in uni.get(cand["label"], []):
        sc = similarity(cand["raw"], name)
        if best is None or sc > best["score"]:
            best = {"key": key, "via": name, "score": sc}
    if best is None:
        return None
    # 같은 점수의 다른 키가 있으면 애매함(복합 이름 등)
    rivals = {k for k, n in uni.get(cand["label"], []) if k != best["key"] and similarity(cand["raw"], n) >= best["score"] - 0.02}
    best["ambiguous"] = sorted(rivals)[:3]
    return best
