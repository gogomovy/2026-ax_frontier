"""데이터 구조 파악 — 열 통계 · 의미 유형 · 키 후보 (Phase M · ONB-04 · 구조 파악 에이전트의 결정론 단계)

LLM 없이도 같은 결과가 나온다(Q182). 값 예시는 개인정보 형식을 가리고, 개인정보로 표시된 열(`pii`)은 값을 보이지 않는다.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import DataProfile, Dataset, utcnow

SEMANTICS = ("identifier", "code", "amount", "rate", "count", "date", "yearmonth", "name", "text", "flag", "number")
SEMANTIC_KO = {"identifier": "식별자", "code": "코드", "amount": "금액", "rate": "비율", "count": "건수", "date": "날짜", "yearmonth": "연월", "name": "이름",
               "text": "문장", "flag": "여부", "number": "수치"}
MEASURES = {"amount", "rate", "count", "number"}  # 사실 수치 — 객체 속성으로 복제하지 않는다(그래프 = 개념 · 계보 · 근거)
_RATE = re.compile(r"(rate|ratio|pct|percent|율|비율|비중)", re.I)
_AMT = re.compile(r"(amt|amount|bal|balance|금액|잔액|충당|한도|손익|자산|부채|exposure|rwa)", re.I)
_CNT = re.compile(r"(cnt|count|num_|건수|개수|인원|좌수)", re.I)
_NAME = re.compile(r"(_nm$|name|명$|이름|title)", re.I)
_YM = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])$")
_DATE = re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}")


def version_sig(versions: list[Any]) -> str:
    return "|".join(f"{v.id}" for v in sorted(versions, key=lambda x: x.id))[:200] or "none"


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _semantic(name: str, label: str, ctype: str, vals: list[Any], unique_ratio: float, distinct: int, n: int) -> str:
    hint = f"{name} {label}"
    if ctype == "bool" or (vals and all(isinstance(v, bool) for v in vals)):
        return "flag"
    if ctype == "date" or (vals and all(isinstance(v, str) and _DATE.match(v) for v in vals[:50])):
        return "date"
    if vals and all(_YM.match(str(v)) for v in vals[:50]):
        return "yearmonth"
    if vals and all(_is_num(v) for v in vals[:200]):
        if _RATE.search(hint):
            return "rate"
        if _CNT.search(hint):
            return "count"
        if _AMT.search(hint):
            return "amount"
        if all(isinstance(v, int) for v in vals[:200]) and unique_ratio >= 0.98 and not _AMT.search(hint):
            return "identifier"
        return "number"
    strs = [str(v) for v in vals[:500]]
    avg = sum(len(s) for s in strs) / max(1, len(strs))
    if _NAME.search(hint) and avg <= 40:
        return "name"
    if unique_ratio >= 0.98 and avg <= 24:
        return "identifier"
    if distinct <= max(30, int(n * 0.05)) and avg <= 30:
        return "code"
    if avg > 40:
        return "text"
    return "name"


def _base_type(ctype: str, semantic: str) -> str:
    if semantic in ("code", "identifier") and ctype in ("str", "", None):
        return "code"
    return {"str": "string", "int": "integer", "num": "decimal", "date": "date", "bool": "boolean"}.get(ctype or "str", "string")


def profile_rows(ds: Dataset, rows: list[dict[str, Any]]) -> dict[str, Any]:
    from nhdip.privacy import mask_text

    n = len(rows)
    pii_cols = {str(c.get("name")) for c in ds.columns or [] if c.get("pii")} | set(((ds.mapping or {}).get("pii") or []))
    defs = {str(c.get("name")): c for c in ds.columns or [] if c.get("name")}
    names = list(defs) or sorted({k for r in rows[:50] for k in r})
    cols: dict[str, Any] = {}
    for name in names:
        c = defs.get(name, {})
        vals = [r.get(name) for r in rows]
        present = [v for v in vals if v not in (None, "")]
        distinct = len({str(v) for v in present})
        unique_ratio = round(distinct / len(present), 4) if present else 0.0
        semantic = _semantic(name, str(c.get("label") or ""), str(c.get("type") or ""), present, unique_ratio, distinct, n)
        nums = [v for v in present if _is_num(v)]
        top = Counter(str(v) for v in present).most_common(5)
        hidden = name in pii_cols
        cols[name] = {
            "label": c.get("label") or name, "type": c.get("type") or "str", "nullRate": round(1 - len(present) / n, 4) if n else 1.0, "distinct": distinct,
            "uniqueRatio": unique_ratio, "semantic": semantic, "semanticKo": SEMANTIC_KO[semantic], "baseType": _base_type(str(c.get("type") or "str"), semantic),
            "min": (min(nums) if nums else (min(map(str, present)) if present and semantic in ("date", "yearmonth") else None)),
            "max": (max(nums) if nums else (max(map(str, present)) if present and semantic in ("date", "yearmonth") else None)),
            "top": [] if hidden else [{"value": mask_text(v)[:60], "n": k} for v, k in top],
            "keyCandidate": bool(present) and unique_ratio == 1.0 and len(present) == n and semantic not in MEASURES,
            "measure": semantic in MEASURES, "pii": hidden,
        }
    keys = list(ds.key_columns or [])
    if keys and n:
        combo = len({tuple(str(r.get(k)) for k in keys) for r in rows})
        key_ok = combo == n
    else:
        key_ok = False
    return {
        "rows": n, "columns": cols, "keyColumns": keys, "keyUnique": key_ok,
        "keyCandidates": [k for k, v in cols.items() if v["keyCandidate"]],
        "measures": [k for k, v in cols.items() if v["measure"]],
        "dimensions": [k for k, v in cols.items() if v["semantic"] in ("identifier", "code", "name")],
        "asOfColumn": ds.as_of_column,
    }


def latest_profile(session: Session, code: str) -> DataProfile | None:
    return session.execute(select(DataProfile).where(DataProfile.dataset_code == code).order_by(DataProfile.created_at.desc(), DataProfile.id.desc()).limit(1)).scalars().first()


def save_profile(session: Session, ds: Dataset, sig: str, profile: dict[str, Any], semantics: dict[str, Any], by: str, run_id: str | None) -> DataProfile:
    row = session.execute(select(DataProfile).where(DataProfile.dataset_code == ds.code, DataProfile.version_sig == sig)).scalars().first()
    if row is None:
        row = DataProfile(dataset_code=ds.code, origin=ds.origin, version_sig=sig)
        session.add(row)
    row.rows, row.profile, row.semantics, row.by, row.workflow_run_id, row.created_at = int(profile.get("rows") or 0), profile, semantics, by[:80], run_id, utcnow()
    session.flush()
    return row


def rule_semantics(ds: Dataset, profile: dict[str, Any]) -> dict[str, Any]:
    """LLM 없을 때의 업무 의미 — 열 이름 · 의미 유형으로 만든 짧은 설명."""
    cols = {k: {"meaning": f"{v['label']} ({v['semanticKo']})", "entity": None} for k, v in (profile.get("columns") or {}).items()}
    dims = profile.get("dimensions") or []
    return {"columns": cols, "entity": ds.name if ds.kind == "master" else None, "summary": f"{ds.name} — 차원 {len(dims)}개 · 측정값 {len(profile.get('measures') or [])}개", "by": "rule"}
