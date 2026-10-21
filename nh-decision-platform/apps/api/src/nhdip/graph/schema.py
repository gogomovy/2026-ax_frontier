"""온톨로지 스키마 v3 — 객체 유형 · 속성 · 링크 유형 · 인터페이스 (Phase M · 요구사항 §30 ONB-01~03 · Q179 · Q180)

팔란티어 온톨로지의 의미 요소를 판(version)이 있는 스키마 JSON 에 필드로 둔다.

  클래스(객체 유형)  label · ko(업무 이름) · kind(object 업무 개체 · concept 개념 · system 계보) · description · key_hint
                    primary_key · title_property · properties[{name, ko, base_type, required, description}]
                    backing[{dataset, key_col, title_col, props{속성: 열}}]   ← 원천 데이터셋(행 = 객체, 열 = 속성)
                    implements[인터페이스 이름] · extractable · resolve · required
  관계(링크 유형)    type · ko · from · to · cardinality(1:1 · 1:N · N:1 · N:N) · inverse · description
                    backing[{dataset, from_col, to_col}]                       ← 한 행의 두 열(외래 키 → 상대 객체 기본 키)
                    extractable · props · allowed · rule_keywords (문서 추출용 — 이전과 같음)
  인터페이스         name · ko · properties[이름]  (공통 모양 — 구현 클래스가 그 속성을 가져야 한다)

여기 함수는 순수하다(DB 는 검증 때 데이터셋 존재 확인에만 쓴다). 변경은 연산(op) 목록으로 하고(`apply_ops`), 에이전트 · 관리자의
변경 제안(ontology_proposal)도 같은 연산을 쓴다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,60}$")
REL_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,60}$")
PROP_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$")
BASE_TYPES = ("string", "integer", "decimal", "date", "boolean", "code")
KINDS = ("object", "concept", "system")
# 참조 관계(§38 CMN)의 from 열 — 행의 열이 아니라 그 자료(Dataset 노드) 자신. 사실 표(키가 여러 열)도 공통 개체를 가리킬 수 있게
DATASET_FROM = "$dataset"
CARDINALITIES = ("1:1", "1:N", "N:1", "N:N")
OPS = ("add_class", "update_class", "add_property", "add_backing", "add_relation", "update_relation", "add_link_backing", "add_alias")

# 업무 이름 기본값 — 스키마에 ko 가 없을 때(이전 판) 화면 · 프롬프트가 쓰는 이름 (Q125 → Phase M 에서 스키마로 옮김)
CLASS_KO = {
    "Dataset": "데이터셋", "DatasetVersion": "데이터셋 버전", "Metric": "지표", "Workflow": "워크플로", "Artifact": "화면 산출물",
    "Document": "문서", "DocClass": "문서 분류", "Issuer": "발행 기관", "PolicyTheme": "정책 주제", "ProductGroup": "상품군",
    "Product": "상품", "Segment": "고객군", "RatingModel": "평가 모형", "BusinessDomain": "사업 부문", "CapitalConstraint": "자본 제약",
    "Candidate": "미확정 후보", "Plan": "수행방안(영업점 공통)",
}
SYSTEM_CLASSES = {"Dataset", "DatasetVersion", "Metric", "Workflow", "Artifact", "Document", "DocClass", "Candidate", "Plan"}
REL_KO = {
    "HAS_VERSION": "버전", "FEEDS": "지표 입력", "DERIVED_FROM": "지표 파생", "USES": "사용", "PRODUCES": "산출", "READS_CLASS": "문서 분류 읽음",
    "DESCRIBES": "설명", "IN_CLASS": "분류", "ISSUED_BY": "발행", "MENTIONS": "언급", "STATES_STANCE": "기조 표명", "SETS_CONSTRAINT": "제약 설정",
    "IN_GROUP": "상품군 소속", "PART_OF_THEME": "정책 주제 소속", "APPLIES_TO": "적용 대상", "MEASURES": "측정", "BELONGS_TO": "소속",
    "LINKED_TO": "연결 분석", "EVIDENCED_BY": "근거 문서", "USES_DATA": "연결 데이터",
}
# 플랫폼이 직접 관리하는 연결 — 활성 스키마 판에 없어도 투영한다(이전 판 스키마로 운영 중인 곳에서도 영업점 공통 연결이 그래프에 나타나게).
# 수행방안 '영업점 참고'(views.plan_share) → 연결 보고서 · 근거 문서 · 데이터셋. 권한은 그래프가 아니라 SQL · ES 규칙이 정한다
PLATFORM_CLASSES = {"Plan"}
PLATFORM_RELS = {"LINKED_TO", "EVIDENCED_BY", "USES_DATA"}


def class_ko(c: dict[str, Any]) -> str:
    return str(c.get("ko") or CLASS_KO.get(str(c.get("label")), c.get("label") or ""))


def rel_ko(r: dict[str, Any]) -> str:
    return str(r.get("ko") or REL_KO.get(str(r.get("type")), r.get("type") or ""))


def class_kind(c: dict[str, Any]) -> str:
    k = c.get("kind")
    if k in KINDS:
        return str(k)
    return "system" if c.get("label") in SYSTEM_CLASSES else ("object" if c.get("backing") else "concept")


def as_dict(schema: Any) -> dict[str, Any]:
    """ORM(OntologySchema) · 사전 → {classes, relations, aliases, interfaces} 깊은 사본."""
    if isinstance(schema, dict):
        src = schema
    else:
        src = {"classes": schema.classes, "relations": schema.relations, "aliases": schema.aliases, "interfaces": getattr(schema, "interfaces", None)}
    return {"classes": copy.deepcopy(list(src.get("classes") or [])), "relations": copy.deepcopy(list(src.get("relations") or [])),
            "aliases": copy.deepcopy(dict(src.get("aliases") or {})), "interfaces": copy.deepcopy(list(src.get("interfaces") or []))}


# ═════════════════════════ 검증 (ONB-03) ═════════════════════════
def _dataset_columns(session: Session | None) -> dict[str, set[str]] | None:
    if session is None:
        return None
    from nhdip.models import Dataset

    return {d.code: {str(c.get("name")) for c in (d.columns or []) if c.get("name")} for d in session.execute(select(Dataset).where(Dataset.active)).scalars()}


def validate_schema(schema: dict[str, Any], session: Session | None = None) -> dict[str, list[str]]:
    """{errors, warnings} — 오류가 있으면 저장 · 적용하지 않는다(422). 경고는 응답에 싣고 저장한다."""
    errors: list[str] = []
    warnings: list[str] = []
    classes = schema.get("classes") or []
    relations = schema.get("relations") or []
    interfaces = {str(i.get("name")): i for i in (schema.get("interfaces") or []) if isinstance(i, dict)}
    ds_cols = _dataset_columns(session)
    labels: set[str] = set()
    for c in classes:
        if not isinstance(c, dict):
            errors.append("클래스 항목이 객체가 아닙니다")
            continue
        label = str(c.get("label") or "")
        if not LABEL_RE.match(label):
            errors.append(f"클래스 라벨 형식 오류: {label or '(빈 값)'}")
            continue
        if label in labels:
            errors.append(f"클래스 라벨 중복: {label}")
        labels.add(label)
        if c.get("kind") is not None and c.get("kind") not in KINDS:
            errors.append(f"{label}: kind 는 {' · '.join(KINDS)}")
        props = c.get("properties") or []
        names: set[str] = set()
        for p in props:
            if not isinstance(p, dict) or not PROP_RE.match(str(p.get("name") or "")):
                errors.append(f"{label}: 속성 이름 형식 오류 {p.get('name') if isinstance(p, dict) else p}")
                continue
            if p["name"] in names:
                errors.append(f"{label}: 속성 중복 {p['name']}")
            names.add(p["name"])
            if p.get("base_type") not in BASE_TYPES:
                errors.append(f"{label}.{p['name']}: base_type 은 {' · '.join(BASE_TYPES)}")
        implicit = {"key", "name"}
        for k in ("primary_key", "title_property"):
            v = c.get(k)
            if v and props and v not in names | implicit:
                errors.append(f"{label}: {k}({v}) 가 속성 목록에 없습니다")
        for b in c.get("backing") or []:
            if not isinstance(b, dict) or not b.get("dataset") or not b.get("key_col"):
                errors.append(f"{label}: 원천(backing)에는 dataset · key_col 이 필요합니다")
                continue
            if ds_cols is not None:
                cols = ds_cols.get(b["dataset"])
                if cols is None:
                    errors.append(f"{label}: 원천 데이터셋 없음 {b['dataset']}")
                    continue
                need = [b["key_col"], *([b["title_col"]] if b.get("title_col") else []), *list((b.get("props") or {}).values())]
                miss = [x for x in need if x not in cols]
                if miss:
                    errors.append(f"{label}: {b['dataset']} 에 없는 열 {', '.join(map(str, miss))}")
            for prop in (b.get("props") or {}):
                if props and prop not in names | implicit:
                    warnings.append(f"{label}: 원천 속성 {prop} 이 속성 목록에 없습니다(문자열로 투영)")
        for iname in c.get("implements") or []:
            itf = interfaces.get(str(iname))
            if itf is None:
                errors.append(f"{label}: 없는 인터페이스 {iname}")
                continue
            lack = [p for p in itf.get("properties") or [] if p not in names | implicit]
            if lack:
                warnings.append(f"{label}: 인터페이스 {iname} 의 속성 {', '.join(lack)} 이 없습니다")
    types: set[tuple[str, str, str]] = set()
    for r in relations:
        if not isinstance(r, dict):
            errors.append("관계 항목이 객체가 아닙니다")
            continue
        rtype = str(r.get("type") or "")
        if not REL_RE.match(rtype):
            errors.append(f"관계 이름 형식 오류(대문자): {rtype or '(빈 값)'}")
            continue
        frm, to = str(r.get("from") or ""), str(r.get("to") or "")
        for end, v in (("from", frm), ("to", to)):
            if v != "*" and v not in labels:
                errors.append(f"{rtype}: {end} 클래스 없음 {v or '(빈 값)'}")
        if "*" in (frm, to):
            warnings.append(f"{rtype}: 끝점이 '*'(모든 클래스) — 가능하면 클래스를 정하세요")
        sig = (rtype, frm, to)
        if sig in types:
            errors.append(f"관계 중복: {rtype} {frm}→{to}")
        types.add(sig)
        if r.get("cardinality") is not None and r.get("cardinality") not in CARDINALITIES:
            errors.append(f"{rtype}: cardinality 는 {' · '.join(CARDINALITIES)}")
        for b in r.get("backing") or []:
            if not isinstance(b, dict) or not b.get("dataset") or not b.get("from_col") or not b.get("to_col"):
                errors.append(f"{rtype}: 원천(backing)에는 dataset · from_col · to_col 이 필요합니다")
                continue
            if "*" in (frm, to):
                errors.append(f"{rtype}: 끝점이 '*' 인 관계에는 원천을 둘 수 없습니다")
            if b["from_col"] == DATASET_FROM and frm != "Dataset":
                errors.append(f"{rtype}: from_col '{DATASET_FROM}'(자료 자신)은 from 이 Dataset 인 참조 관계에만 씁니다")
            if ds_cols is not None:
                cols = ds_cols.get(b["dataset"])
                if cols is None:
                    errors.append(f"{rtype}: 원천 데이터셋 없음 {b['dataset']}")
                elif any(x not in cols for x in (b["from_col"], b["to_col"]) if x != DATASET_FROM):
                    errors.append(f"{rtype}: {b['dataset']} 에 없는 열 {b['from_col']} · {b['to_col']}")
    for label in (schema.get("aliases") or {}):
        if label not in labels:
            errors.append(f"별칭의 클래스 없음: {label}")
    for name, itf in interfaces.items():
        if not LABEL_RE.match(name):
            errors.append(f"인터페이스 이름 형식 오류: {name}")
    return {"errors": errors, "warnings": warnings}


# ═════════════════════════ 연산 (ONB-09) ═════════════════════════
def op_key(op: dict[str, Any]) -> str:
    """같은 변경인지 가르는 열쇠 — 대기 중 제안 · 이미 반영된 연산과 겹치지 않게."""
    kind = op.get("op")
    if kind == "add_class":
        return f"add_class:{(op.get('class') or {}).get('label')}"
    if kind in ("update_class", "add_property", "add_backing"):
        tail = (op.get("property") or {}).get("name") if kind == "add_property" else (op.get("backing") or {}).get("dataset") if kind == "add_backing" else json.dumps(op.get("set") or {}, sort_keys=True, ensure_ascii=False)
        return f"{kind}:{op.get('label')}:{tail}"
    if kind == "add_relation":
        r = op.get("relation") or {}
        return f"add_relation:{r.get('type')}:{r.get('from')}:{r.get('to')}"
    if kind in ("update_relation", "add_link_backing"):
        tail = (op.get("backing") or {}).get("dataset") if kind == "add_link_backing" else json.dumps(op.get("set") or {}, sort_keys=True, ensure_ascii=False)
        return f"{kind}:{op.get('type')}:{tail}"
    if kind == "add_alias":
        return f"add_alias:{op.get('label')}:{op.get('key')}:{','.join(sorted(map(str, op.get('aliases') or [])))}"
    return f"{kind}:{hashlib.sha1(json.dumps(op, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]}"


def _cls(s: dict[str, Any], label: str) -> dict[str, Any] | None:
    return next((c for c in s["classes"] if c.get("label") == label), None)


def _rel(s: dict[str, Any], rtype: str) -> list[dict[str, Any]]:
    return [r for r in s["relations"] if r.get("type") == rtype]


UPDATABLE_CLASS = ("ko", "description", "kind", "primary_key", "title_property", "key_hint", "implements")
UPDATABLE_REL = ("ko", "description", "cardinality", "inverse")


def apply_ops(schema: dict[str, Any], ops: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """(새 스키마, 적용한 연산, 건너뛴 연산[{op, reason}]) — 이미 있는 것은 건너뛴다(멱등). 입력은 바꾸지 않는다."""
    s = as_dict(schema)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    def skip(op: dict[str, Any], why: str) -> None:
        skipped.append({"op": op, "reason": why})

    for op in ops or []:
        kind = op.get("op") if isinstance(op, dict) else None
        if kind not in OPS:
            skip(op, f"알 수 없는 연산: {kind}")
            continue
        if kind == "add_class":
            c = dict(op.get("class") or {})
            if not c.get("label"):
                skip(op, "label 없음")
            elif _cls(s, c["label"]):
                skip(op, f"이미 있는 클래스 {c['label']}")
            else:
                c.setdefault("extractable", False)
                c.setdefault("required", [])
                s["classes"].append(c)
                applied.append(op)
            continue
        if kind in ("update_class", "add_property", "add_backing"):
            c = _cls(s, str(op.get("label") or ""))
            if c is None:
                skip(op, f"클래스 없음 {op.get('label')}")
                continue
            if kind == "update_class":
                changed = False
                for k, v in (op.get("set") or {}).items():
                    if k in UPDATABLE_CLASS and c.get(k) != v:
                        c[k] = v
                        changed = True
                (applied if changed else skipped).append(op if changed else {"op": op, "reason": "바뀐 값 없음"})
            elif kind == "add_property":
                p = dict(op.get("property") or {})
                if any(x.get("name") == p.get("name") for x in c.get("properties") or []):
                    skip(op, f"이미 있는 속성 {p.get('name')}")
                else:
                    c.setdefault("properties", []).append(p)
                    applied.append(op)
            else:
                b = dict(op.get("backing") or {})
                if any(x.get("dataset") == b.get("dataset") for x in c.get("backing") or []):
                    skip(op, f"이미 원천인 데이터셋 {b.get('dataset')}")
                else:
                    c.setdefault("backing", []).append(b)
                    applied.append(op)
            continue
        if kind == "add_relation":
            r = dict(op.get("relation") or {})
            same = [x for x in _rel(s, str(r.get("type") or "")) if x.get("from") == r.get("from") and x.get("to") == r.get("to")]
            if not r.get("type"):
                skip(op, "type 없음")
            elif same:
                # 같은 관계가 이미 있으면 원천만 더한다
                added = False
                for b in r.get("backing") or []:
                    if not any(x.get("dataset") == b.get("dataset") and x.get("from_col") == b.get("from_col") for x in same[0].get("backing") or []):
                        same[0].setdefault("backing", []).append(b)
                        added = True
                (applied if added else skipped).append(op if added else {"op": op, "reason": f"이미 있는 관계 {r['type']}"})
            elif _rel(s, str(r["type"])):
                skip(op, f"같은 이름 {r['type']} 의 관계가 다른 끝점으로 있음 — 이름을 바꾸세요")
            else:
                r.setdefault("extractable", False)
                s["relations"].append(r)
                applied.append(op)
            continue
        if kind in ("update_relation", "add_link_backing"):
            rels = _rel(s, str(op.get("type") or ""))
            if not rels:
                skip(op, f"관계 없음 {op.get('type')}")
                continue
            r = rels[0]
            if kind == "update_relation":
                changed = False
                for k, v in (op.get("set") or {}).items():
                    if k in UPDATABLE_REL and r.get(k) != v:
                        r[k] = v
                        changed = True
                (applied if changed else skipped).append(op if changed else {"op": op, "reason": "바뀐 값 없음"})
            else:
                b = dict(op.get("backing") or {})
                if any(x.get("dataset") == b.get("dataset") and x.get("from_col") == b.get("from_col") for x in r.get("backing") or []):
                    skip(op, "이미 있는 원천")
                else:
                    r.setdefault("backing", []).append(b)
                    applied.append(op)
            continue
        if kind == "add_alias":
            label, key = str(op.get("label") or ""), str(op.get("key") or "")
            if not _cls(s, label) or not key:
                skip(op, f"클래스 · 키 없음 {label}:{key}")
                continue
            entry = s["aliases"].setdefault(label, {}).setdefault(key, [])
            new = [a for a in (op.get("aliases") or []) if isinstance(a, str) and a.strip() and a not in entry]
            if not new:
                skip(op, "이미 있는 별칭")
            else:
                entry.extend(new)
                applied.append(op)
    return s, applied, skipped


def diff_schema(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """판 사이 차이 요약 — 화면의 '바뀐 것' 목록."""
    o, n = as_dict(old), as_dict(new)
    oc = {c.get("label"): c for c in o["classes"]}
    nc = {c.get("label"): c for c in n["classes"]}
    orl = {(r.get("type"), r.get("from"), r.get("to")): r for r in o["relations"]}
    nrl = {(r.get("type"), r.get("from"), r.get("to")): r for r in n["relations"]}
    alias_added = []
    for label, entries in n["aliases"].items():
        for key, al in (entries or {}).items():
            before = set(((o["aliases"].get(label) or {}).get(key)) or [])
            extra = [a for a in al or [] if a not in before]
            if extra:
                alias_added.append({"label": label, "key": key, "aliases": extra})
    return {
        "classesAdded": sorted(k for k in nc if k not in oc),
        "classesRemoved": sorted(k for k in oc if k not in nc),
        "classesChanged": sorted(k for k in nc if k in oc and json.dumps(nc[k], sort_keys=True, ensure_ascii=False) != json.dumps(oc[k], sort_keys=True, ensure_ascii=False)),
        "relationsAdded": [f"{t}:{f}→{to}" for (t, f, to) in nrl if (t, f, to) not in orl],
        "relationsRemoved": [f"{t}:{f}→{to}" for (t, f, to) in orl if (t, f, to) not in nrl],
        "relationsChanged": [f"{t}:{f}→{to}" for (t, f, to), r in nrl.items() if (t, f, to) in orl and json.dumps(r, sort_keys=True, ensure_ascii=False) != json.dumps(orl[(t, f, to)], sort_keys=True, ensure_ascii=False)],
        "aliasesAdded": alias_added,
    }


def schema_summary(schema: dict[str, Any]) -> dict[str, Any]:
    s = as_dict(schema)
    backed = [c["label"] for c in s["classes"] if c.get("backing")]
    return {"classes": len(s["classes"]), "relations": len(s["relations"]), "backedClasses": backed, "linkBacked": [r["type"] for r in s["relations"] if r.get("backing")],
            "interfaces": [i.get("name") for i in s["interfaces"]], "aliasKeys": sum(len(v or {}) for v in s["aliases"].values())}
