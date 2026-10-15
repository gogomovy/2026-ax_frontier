"""온톨로지 품질 검증 (Phase M · ONB-08 · 규칙 에이전트 onto_qa)

점검 결과는 [온톨로지 › 구축 파이프라인] · [에이전틱 파이프라인]에 등급(ok 정상 · warn 주의 · risk 위험)으로 보인다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, ExtractionIssue, source

from .schema import as_dict, validate_schema


def run_checks(session: Session, schema: Any, batch: Any, rows_by_ds: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(code: str, title: str, ok: bool, severity: str, detail: str, count: int = 0, items: list[Any] | None = None) -> None:
        checks.append({"code": code, "title": title, "ok": ok, "severity": "ok" if ok else severity, "detail": detail, "count": count, "items": (items or [])[:20]})

    v = validate_schema(as_dict(schema), session)
    add("schema", "스키마 정합성", not v["errors"], "risk", f"오류 {len(v['errors'])} · 경고 {len(v['warnings'])}", len(v["errors"]), v["errors"] + v["warnings"])
    backed = {bk.get("dataset") for c in schema.classes or [] for bk in c.get("backing") or []}
    from nhdip.data.sources import Resolver

    res = Resolver(session)

    def mapped(d: Dataset) -> bool:  # 정의 자체 또는 이어진 업무 구성 '자료'의 온톨로지 연결(Phase O)
        return any(m.get("nodes") or m.get("concepts") or m.get("edges") for m in [d.mapping or {}, *res.mappings_for(d.code)])

    uncovered = [d.code for d in session.execute(select(Dataset).where(Dataset.active)).scalars() if d.code not in backed and not mapped(d)]
    add("coverage", "온톨로지에 연결되지 않은 데이터셋", not uncovered, "warn", f"{len(uncovered)}개 — 구축 에이전트가 객체 유형 · 개념 연결을 제안합니다" if uncovered else "모든 데이터셋이 객체 · 개념으로 연결됨", len(uncovered), uncovered)
    rejected = sorted(set(getattr(batch, "rejected", []) or []))
    add("rejected", "스키마에 없어 버려진 라벨 · 관계", not rejected, "warn", f"{len(rejected)}종", len(rejected), rejected)
    dang = batch.dangling() if hasattr(batch, "dangling") else {}
    total_rels = sum(len(x) for x in getattr(batch, "rels", {}).values()) or 1
    n_dang = sum(dang.values())
    add("dangling", "끝점이 없어 빠지는 관계", n_dang / total_rels <= 0.05, "warn", f"{n_dang}건 / 전체 {total_rels}건", n_dang, [f"{k} {v}건" for k, v in sorted(dang.items(), key=lambda x: -x[1])])
    dup_items, card_items = [], []
    for c in schema.classes or []:
        for bk in c.get("backing") or []:
            rows = rows_by_ds.get(bk.get("dataset"), [])
            keys = [str(r.get(bk.get("key_col"))) for r in rows if r.get(bk.get("key_col")) not in (None, "")]
            d = len(keys) - len(set(keys))
            if d:
                dup_items.append(f"{c['label']} ← {bk.get('dataset')}.{bk.get('key_col')} 중복 {d}건")
    for r in schema.relations or []:
        if r.get("cardinality") not in ("N:1", "1:1"):
            continue
        for bk in r.get("backing") or []:
            per: dict[str, set[str]] = {}
            for row in rows_by_ds.get(bk.get("dataset"), []):
                f, t = row.get(bk.get("from_col")), row.get(bk.get("to_col"))
                if f not in (None, "") and t not in (None, ""):
                    per.setdefault(str(f), set()).add(str(t))
            bad = sum(1 for s in per.values() if len(s) > 1)
            if bad:
                card_items.append(f"{r['type']}({r['cardinality']}) — 하나에 여러 상대가 있는 {bad}건")
    add("key_unique", "원천 기본 키 중복", not dup_items, "risk", f"{len(dup_items)}곳", len(dup_items), dup_items)
    add("cardinality", "다중도 위반", not card_items, "warn", f"{len(card_items)}곳", len(card_items), card_items)
    n_cand = 0
    stale = 0
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in session.execute(select(t.document).where(t.document.is_current)).scalars():
            ex = d.extraction or {}
            n_cand += sum(1 for e in ex.get("entities") or [] if e.get("label") == "Candidate")
            if ex and int(ex.get("schema_version") or 0) < int(schema.version or 0):
                stale += 1
    open_issues = session.execute(select(func.count()).select_from(ExtractionIssue).where(ExtractionIssue.status == "open")).scalar() or 0
    add("candidates", "미해석 후보 적체", n_cand <= 20, "warn", f"후보 {n_cand}개 · 검토 대기 {open_issues}건 — 개체 해소 에이전트가 별칭을 제안합니다", n_cand)
    add("stale_extraction", "이전 스키마로 추출된 문서", stale == 0, "warn", f"{stale}건 — 구축 실행마다 일부씩 다시 추출합니다", stale)
    grade = "risk" if any(c["severity"] == "risk" for c in checks) else ("warn" if any(c["severity"] == "warn" for c in checks) else "ok")
    return {"grade": grade, "checks": checks, "schemaVersion": schema.version, "nodes": sum(len(x) for x in getattr(batch, "nodes", {}).values()), "relations": total_rels if total_rels > 1 else 0}
