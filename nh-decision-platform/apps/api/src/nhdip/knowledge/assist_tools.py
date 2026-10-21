"""AI 어시스턴트 도구 — 온톨로지 조회 · 반영된 자료 집계 (Phase M · 요구사항 LLM-P06 · DOB-08 · Q196).

도구가 켜진 에이전트(query_assistant · tools_enabled)만 쓴다. LLM 계층(llm.tools)은 스키마와 실행 함수만 받는다.

  onto_find       이름 → 온톨로지 대표 키(별칭 사전 해석) · 클래스 업무 이름. 클래스를 모르면 모든 클래스에서 찾는다
  onto_neighbors  클래스(또는 대표 키) → 들고 나는 링크 유형(업무 이름 · 다중도 · 원천 데이터셋). Neo4j 가 있으면 그 키의 이웃 노드(최대 20)
  data_aggregate  반영된 정형 자료(현재 버전) → 합계 · 건수 · 평균 · 최소 · 최대(그룹 · 같음 조건). 합계 · 평균은 계산 커널(SUM · RATIO)로.
                  행 원문은 돌려주지 않는다. 화면 가림 열 · 개인정보 형식 값이 든 열은 그룹 · 조건에 못 쓴다. 데이터셋 화면 권한(datasets)이 있어야 한다
                  — 없으면 영업점 공통으로 연결된 데이터셋(영업점 참고 수행방안의 연결 보고서를 계산하는 자료)만.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Dataset

from .access import AccessContext

DATA_RESOURCE = "datasets"
OPS = ("sum", "count", "avg", "min", "max")
MAX_GROUPS = 30

SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "onto_find", "description": "온톨로지에서 이름(상품 · 상품군 · 모형 · 영업점 등)을 찾아 대표 키와 클래스를 돌려준다",
        "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "찾을 이름"}, "label": {"type": "string", "description": "클래스(영문 라벨, 모르면 비움)"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "onto_neighbors", "description": "클래스(또는 그 클래스의 대표 키)와 연결된 링크 유형 · 이웃을 돌려준다",
        "parameters": {"type": "object", "properties": {"label": {"type": "string", "description": "클래스(영문 라벨)"}, "key": {"type": "string", "description": "대표 키(선택)"}}, "required": ["label"]}}},
    {"type": "function", "function": {
        "name": "data_aggregate", "description": "반영된 정형 자료를 계산 커널로 집계한다(합계 · 건수 · 평균 · 최소 · 최대, 그룹 · 조건). 행 원문은 주지 않는다",
        "parameters": {"type": "object", "properties": {
            "dataset": {"type": "string", "description": "데이터셋 코드"}, "measure": {"type": "string", "description": "집계할 숫자 열(count 는 생략 가능)"},
            "op": {"type": "string", "enum": list(OPS)}, "group_by": {"type": "string", "description": "그룹 열(선택)"},
            "filters": {"type": "object", "description": "조건(선택) — 같음 {열: 값}, 비교 {열: {\"gte\"|\"gt\"|\"lte\"|\"lt\"|\"ne\"|\"eq\": 값}}, 목록 {열: {\"in\": [값, ...]}}. 여러 열은 모두 만족"}},
            "required": ["dataset", "op"]}}},
]


def _all_data(ctx: AccessContext) -> bool:
    return bool(ctx.is_admin or (ctx.resources is not None and DATA_RESOURCE in ctx.resources))


def can_aggregate(ctx: AccessContext) -> bool:
    """데이터셋 화면 권한이 있거나, 영업점 공통으로 연결된 데이터셋(영업점 참고 수행방안의 연결 보고서를 계산하는 자료)이 있을 때."""
    return _all_data(ctx) or bool(ctx.grant_datasets)


def _schema(session: Session):
    from nhdip.graph.projection import active_schema

    return active_schema(session)


def onto_find(session: Session, name: str, label: str | None = None) -> dict[str, Any]:
    from nhdip.graph.extraction import Resolver

    sc = _schema(session)
    if sc is None:
        return {"found": [], "note": "활성 온톨로지 스키마 없음"}
    res = Resolver(sc)
    labels = [label] if label else [c["label"] for c in sc.classes]
    found = []
    for lb in labels:
        if lb not in res.classes:
            continue
        key = res.match(lb, name)
        if key:
            c = res.classes[lb]
            found.append({"label": lb, "ko": c.get("ko") or lb, "key": key, "aliases": ((sc.aliases or {}).get(lb) or {}).get(key, [])[:8]})
    return {"name": name, "found": found[:10], **({} if found else {"note": "별칭 사전에서 찾지 못함 — 다른 이름으로 다시 찾거나 문서 검색 결과를 쓴다"})}


def onto_neighbors(session: Session, label: str, key: str | None = None) -> dict[str, Any]:
    sc = _schema(session)
    if sc is None:
        return {"links": [], "note": "활성 온톨로지 스키마 없음"}
    classes = {c["label"]: c for c in sc.classes}
    if label not in classes:
        return {"error": f"없는 클래스: {label}", "classes": sorted(classes)[:40]}
    ko = {lb: (c.get("ko") or lb) for lb, c in classes.items()}
    links = []
    for r in sc.relations or []:
        if label not in (r.get("from"), r.get("to")):
            continue
        out = r.get("from") == label
        links.append({"type": r["type"], "ko": r.get("ko") or r["type"], "direction": "out" if out else "in", "other": r["to"] if out else r["from"],
                      "otherKo": ko.get(r["to"] if out else r["from"]), "cardinality": r.get("cardinality"), "datasets": sorted({b.get("dataset") for b in r.get("backing") or [] if b.get("dataset")})})
    out: dict[str, Any] = {"label": label, "ko": ko[label], "links": links[:40], "datasets": sorted({b.get("dataset") for b in classes[label].get("backing") or [] if b.get("dataset")})}
    if key:
        try:
            from nhdip.graph.neo4j_client import run, safe_name

            rows = run(f"MATCH (n:{safe_name(label)} {{key: $key}})-[r]-(m) RETURN type(r) AS rel, labels(m)[0] AS label, m.key AS key, m.name AS name LIMIT 20", key=key)
            out["neighbors"] = [{"rel": x["rel"], "label": x["label"], "key": x["key"], "name": x.get("name")} for x in rows]
        except Exception as exc:  # noqa: BLE001 — Neo4j 가 없거나 꺼져 있으면 스키마 수준으로만
            out["neighbors"] = None
            out["note"] = f"그래프 저장소를 쓸 수 없어 링크 유형만 — {type(exc).__name__}"
    return out


def _num(v: Any) -> Decimal | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


CMP_OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "in")


def _conditions(filters: dict[str, Any]) -> tuple[list[tuple[str, Any]], str | None]:
    """조건 {열: 값} 또는 {열: {gte|gt|lte|lt|ne|eq|in: 값}} → (열, 판정 함수) 목록. 크기 비교는 숫자로(숫자가 아니면 그 행은 빠진다).
    후속 질문으로 기준을 바꿔 집계할 때('등급 7 이상만', '잔액 1억 넘는 것') 같은 조건을 도구로 계산한다(발표 · 수시 질의)."""
    out: list[tuple[str, Any]] = []
    for col, spec in filters.items():
        if not isinstance(spec, dict):
            want = str(spec)
            out.append((col, lambda v, w=want: str(v) == w))
            continue
        for op, arg in spec.items():
            if op not in CMP_OPS:
                return [], f"조건 연산은 {', '.join(CMP_OPS)} 중 하나: {op}"
            if op == "in":
                vals = {str(x) for x in (arg if isinstance(arg, list) else [arg])}
                out.append((col, lambda v, s=vals: str(v) in s))
            elif op in ("eq", "ne"):
                want = str(arg)
                out.append((col, (lambda v, w=want: str(v) == w) if op == "eq" else (lambda v, w=want: str(v) != w)))
            else:
                ref = _num(arg)
                if ref is None:
                    return [], f"{col} 의 {op} 비교 값은 숫자여야 합니다"

                def cmp(v: Any, o: str = op, r: Decimal = ref) -> bool:
                    x = _num(v)
                    if x is None:
                        return False
                    return {"gt": x > r, "gte": x >= r, "lt": x < r, "lte": x <= r}[o]

                out.append((col, cmp))
    return out, None


def _blocked_columns(session: Session, ds: Dataset, rows: list[dict[str, Any]]) -> set[str]:
    """그룹 · 조건에 못 쓰는 열 — 화면 가림 열 + 값에 개인정보 형식이 보이는 열."""
    from nhdip.privacy import PATTERNS, policy

    out = set(policy(session).get("display_mask_columns") or [])
    for c in ds.columns or []:
        name = c.get("name")
        for r in rows[:200]:
            v = r.get(name)
            if isinstance(v, str) and len(v) >= 6 and any(p.search(v) for p in PATTERNS.values()):
                out.add(name)
                break
    return out


def data_aggregate(session: Session, ctx: AccessContext, dataset: str, op: str, measure: str | None = None, group_by: str | None = None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    from nhdip.calc import execute
    from nhdip.data.datasets import current_rows

    if not can_aggregate(ctx):
        return {"error": "데이터셋 화면 권한이 없어 자료를 집계할 수 없습니다"}
    if op not in OPS:
        return {"error": f"op 는 {', '.join(OPS)} 중 하나"}
    shared_only = not _all_data(ctx)
    allowed = set(ctx.grant_datasets or {}) if shared_only else None
    ds = session.get(Dataset, dataset)
    if ds is None or not ds.active or (allowed is not None and ds.code not in allowed):
        if allowed is not None:
            # 영업점 공통 — 연결된 데이터셋만 있다는 것만 알린다(다른 자료의 존재를 드러내지 않는다)
            return {"error": f"{ctx.grant_label}으로 연결된 데이터셋이 아닙니다: {dataset}", "datasets": sorted(allowed)[:40]}
        names = [d.code for d in session.execute(select(Dataset).where(Dataset.active).order_by(Dataset.code)).scalars()][:40]
        return {"error": f"없는 데이터셋: {dataset}", "datasets": names}
    cols = {c.get("name"): c for c in ds.columns or []}
    vs, rows = current_rows(session, ds)
    if not rows:
        return {"dataset": ds.code, "error": "반영된 현재 버전이 없습니다"}
    blocked = _blocked_columns(session, ds, rows)
    if op != "count":
        if not measure or measure not in cols:
            return {"error": f"measure 열이 정의에 없습니다: {measure}", "columns": [k for k, c in cols.items() if c.get("type") in ("int", "num")]}
        if cols[measure].get("type") not in ("int", "num"):
            return {"error": f"{measure} 는 숫자 열이 아닙니다"}
    for name in [group_by, *((filters or {}).keys())]:
        if name and name not in cols:
            return {"error": f"정의에 없는 열: {name}"}
        if name and name in blocked:
            return {"error": f"{name} 열은 개인정보 · 가림 열이라 그룹 · 조건에 쓸 수 없습니다"}
    conds, bad = _conditions(filters or {})
    if bad:
        return {"error": bad}
    flt = {k: (v if isinstance(v, dict) else str(v)) for k, v in (filters or {}).items()}
    sel = [r for r in rows if all(c(r.get(k)) for k, c in conds)]

    def agg(rs: list[dict[str, Any]]) -> dict[str, Any]:
        if op == "count":
            return {"value": len(rs), "rows": len(rs)}
        vals = [x for x in (_num(r.get(measure)) for r in rs) if x is not None]
        if not vals:
            return {"value": None, "rows": len(rs)}
        if op in ("sum", "avg"):
            total = execute("SUM", {"values": [str(v) for v in vals]}).value
            value = total if op == "sum" else execute("RATIO", {"a": str(total), "b": len(vals)}).value
        else:
            value = min(vals) if op == "min" else max(vals)
        return {"value": None if value is None else str(value), "rows": len(rs)}

    out: dict[str, Any] = {"dataset": ds.code, "name": ds.name, "op": op, "measure": measure, "unit": (cols.get(measure) or {}).get("unit"), "filters": flt,
                           "asOf": vs.as_of.isoformat() if vs is not None and vs.as_of else None, "version": vs.version if vs is not None else None,
                           "by": "계산 커널(SUM · RATIO)" if op in ("sum", "avg") else "집계"}
    if group_by:
        groups: dict[str, list[dict[str, Any]]] = {}
        for r in sel:
            groups.setdefault(str(r.get(group_by)), []).append(r)
        items = sorted(({"group": g, **agg(rs)} for g, rs in groups.items()), key=lambda x: str(x["group"]))
        out.update(groupBy=group_by, groups=items[:MAX_GROUPS], groupCount=len(items), **({"truncated": True} if len(items) > MAX_GROUPS else {}))
    else:
        out.update(agg(sel))
    return out


def build(session: Session, ctx: AccessContext):
    """chat_with_tools(extra=…) 에 넘길 도구 묶음. 자료 집계는 권한이 있을 때만 싣는다."""
    from nhdip.llm.tools import ExtraTools

    schemas = [s for s in SCHEMAS if s["function"]["name"] != "data_aggregate" or can_aggregate(ctx)]
    if can_aggregate(ctx) and not _all_data(ctx):
        # 영업점 공통 — 연결된 데이터셋 코드만 쓸 수 있다고 도구 설명에 적는다
        codes = ", ".join(sorted(ctx.grant_datasets or {})[:20])
        schemas = [
            {**s, "function": {**s["function"], "description": f"{s['function']['description']} — {ctx.grant_label}으로 연결된 데이터셋만: {codes}"}} if s["function"]["name"] == "data_aggregate" else s
            for s in schemas
        ]

    def run(name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "onto_find":
            return onto_find(session, str(args.get("name") or ""), args.get("label") or None)
        if name == "onto_neighbors":
            return onto_neighbors(session, str(args.get("label") or ""), args.get("key") or None)
        if name == "data_aggregate":
            f = args.get("filters") if isinstance(args.get("filters"), dict) else None
            return data_aggregate(session, ctx, str(args.get("dataset") or ""), str(args.get("op") or ""), args.get("measure") or None, args.get("group_by") or None, f)
        return {"error": f"unknown tool {name}"}

    return ExtraTools(schemas=schemas, run=run)
