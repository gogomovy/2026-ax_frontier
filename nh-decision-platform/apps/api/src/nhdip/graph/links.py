"""링크 발견 · 객체 유형 후보 — 결정론 단계 (Phase M · ONB-05 · ONB-06 · Q182)

객체 유형 후보: 원천(backing) · 매핑이 없는 데이터셋 중 키가 하나로 정해지는 것(마스터 · 단일 키) → 기존 클래스(값이 그 클래스 키에 들어맞으면) 또는 새 객체 유형.
링크 후보: 데이터셋의 차원 열(식별자 · 코드 · 이름) 값이 다른 객체 유형의 기본 키(원천 행 키 · 별칭 사전 키 · 별칭)에 포함되는 비율(포함률)로 찾는다.
다중도는 데이터로 정한다(그 열 값이 행마다 다르면 1:1, 아니면 N:1).
"""
from __future__ import annotations

import re
from typing import Any

from .schema import CLASS_KO, class_kind


def snake(label: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", label).upper()


def pascal(code: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", code.lower())
    out = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return out if out and out[0].isalpha() else f"Obj{out}"


def class_universes(schema: Any, rows_by_ds: dict[str, list[dict[str, Any]]], resolver: Any) -> dict[str, dict[str, Any]]:
    """{클래스: {keys: set, aliases: {정규화 별칭: 키}, backing: [데이터셋]}} — 링크 대상이 될 수 있는 객체 유형의 키 모음."""
    out: dict[str, dict[str, Any]] = {}
    for c in schema.classes or []:
        label = c.get("label")
        if class_kind(c) == "system" and label not in ("Issuer",):
            continue
        keys: set[str] = set()
        for bk in c.get("backing") or []:
            for r in rows_by_ds.get(bk.get("dataset"), []):
                v = r.get(bk.get("key_col"))
                if v not in (None, ""):
                    keys.add(str(v))
        amap = (resolver.alias.get(label) or {}) if resolver is not None else {}
        keys |= set(amap.values())
        if keys:
            out[label] = {"keys": keys, "aliases": amap, "backing": [bk.get("dataset") for bk in c.get("backing") or []]}
    return out


def _hit(v: str, uni: dict[str, Any], resolver: Any, label: str) -> bool:
    if v in uni["keys"]:
        return True
    return bool(resolver is not None and uni["aliases"] and resolver.match(label, v))


def backed_by(schema: Any) -> dict[str, tuple[str, str]]:
    """{데이터셋: (클래스, 키 열)} — 데이터셋 행을 객체로 쓰는 클래스(원천 · 이전 매핑 nodes 포함은 호출자가 더함)."""
    out: dict[str, tuple[str, str]] = {}
    for c in schema.classes or []:
        for bk in c.get("backing") or []:
            if bk.get("dataset") and bk.get("key_col"):
                out.setdefault(bk["dataset"], (c["label"], bk["key_col"]))
    return out


def object_type_candidates(datasets: list[Any], profiles: dict[str, dict[str, Any]], schema: Any, rows_by_ds: dict[str, list[dict[str, Any]]], resolver: Any, policy: dict[str, Any]) -> list[dict[str, Any]]:
    """원천 · 매핑이 없는 데이터셋 → 객체 유형 제안 초안(규칙). 사실 수치 열은 속성으로 넣지 않는다."""
    backed = backed_by(schema)
    unis = class_universes(schema, rows_by_ds, resolver)
    labels = {c.get("label") for c in schema.classes or []}
    out: list[dict[str, Any]] = []
    for ds in datasets:
        prof = profiles.get(ds.code)
        if not prof or ds.code in backed or (ds.mapping or {}).get("nodes"):
            continue
        cols = prof.get("columns") or {}
        keys = list(ds.key_columns or [])
        key = keys[0] if len(keys) == 1 else next((k for k in prof.get("keyCandidates") or [] if cols.get(k, {}).get("semantic") in ("identifier", "code")), None)
        if not key or not prof.get("rows"):
            continue
        if len(keys) > 1 and ds.kind != "master":
            continue  # 여러 열이 함께 키인 사실 표(기간 × 지점 × 상품)는 객체가 아니라 사건 기록 — 링크 후보로만
        vals = {str(r.get(key)) for r in rows_by_ds.get(ds.code, []) if r.get(key) not in (None, "")}
        # 기존 클래스에 들어맞는지(값 대부분이 그 클래스 키) → 그 클래스의 원천으로
        best, best_ratio = None, 0.0
        for label, uni in unis.items():
            if not vals:
                break
            ratio = sum(1 for v in vals if _hit(v, uni, resolver, label)) / len(vals)
            if ratio > best_ratio:
                best, best_ratio = label, ratio
        title = next((k for k, v in cols.items() if v.get("semantic") == "name" and k != key), None)
        props = {k: k for k, v in cols.items() if k not in (key, title) and v.get("semantic") in ("code", "name", "date", "yearmonth", "flag") and not v.get("pii")}
        props = dict(list(props.items())[:8])
        target = best if best and best_ratio >= float(policy.get("link_min_containment", 0.95)) else None
        label = target or pascal(ds.code)
        n = 2
        while not target and label in labels:
            label, n = f"{pascal(ds.code)}{n}", n + 1
        out.append({
            "dataset": ds.code, "datasetName": ds.name, "existing": bool(target), "label": label, "ko": (CLASS_KO.get(label) if target else None) or ds.name,
            "key_col": key, "title_col": title, "props": props, "containment": round(best_ratio, 4) if target else None,
            "properties": [{"name": p, "ko": cols[c].get("label") or p, "base_type": cols[c].get("baseType", "string"), "required": False} for p, c in props.items()],
            "confidence": round(0.95 if target else (0.85 if ds.kind == "master" else 0.7), 2),
        })
    return out


def link_candidates(datasets: list[Any], profiles: dict[str, dict[str, Any]], schema: Any, rows_by_ds: dict[str, list[dict[str, Any]]], resolver: Any, policy: dict[str, Any],
                    planned: dict[str, tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """{dataset, from_class, from_col, to_class, to_col, containment, distinct, cardinality} — from 객체(데이터셋 행 객체)가 있어야 한다."""
    backed = {**backed_by(schema), **(planned or {})}
    unis = class_universes(schema, rows_by_ds, resolver)
    have = {(r.get("from"), r.get("to")) for r in schema.relations or []}
    min_c, min_d = float(policy.get("link_min_containment", 0.95)), int(policy.get("link_min_distinct", 2))
    out: list[dict[str, Any]] = []
    for ds in datasets:
        if ds.code not in backed:
            continue
        from_class, key_col = backed[ds.code]
        prof = profiles.get(ds.code) or {}
        rows = rows_by_ds.get(ds.code, [])
        for col, meta in (prof.get("columns") or {}).items():
            if col == key_col or meta.get("semantic") not in ("identifier", "code", "name") or meta.get("pii"):
                continue
            vals = {str(r.get(col)) for r in rows if r.get(col) not in (None, "")}
            if len(vals) < min_d:
                continue
            for label, uni in unis.items():
                if label == from_class or (from_class, label) in have:
                    continue
                ratio = sum(1 for v in vals if _hit(v, uni, resolver, label)) / len(vals)
                if ratio < min_c:
                    continue
                per_key: dict[str, set[str]] = {}
                for r in rows:
                    k, v = r.get(key_col), r.get(col)
                    if k not in (None, "") and v not in (None, ""):
                        per_key.setdefault(str(k), set()).add(str(v))
                many = any(len(v) > 1 for v in per_key.values())
                card = "N:N" if many else ("1:1" if meta.get("uniqueRatio") == 1.0 else "N:1")
                out.append({"dataset": ds.code, "from_class": from_class, "from_col": key_col, "to_class": label, "to_col": col, "containment": round(ratio, 4),
                            "distinct": len(vals), "cardinality": card, "type": f"HAS_{snake(label)}" if card != "N:1" else f"IN_{snake(label)}",
                            "ko": f"{CLASS_KO.get(label, label)} 연결", "confidence": round(min(0.99, 0.6 + 0.4 * ratio), 2)})
    # 같은 (from, to) 는 포함률 높은 열 하나만
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for c in out:
        k = (c["from_class"], c["to_class"])
        if k not in best or c["containment"] > best[k]["containment"]:
            best[k] = c
    return list(best.values())
