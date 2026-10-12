"""문서 → 온톨로지 구조화 (설계 §19.3 LLM 구조화 계약).

1) LLM(에이전트 ontology_extractor)이 청크별로 {entities, relations} JSON 을 낸다.
2) 검증: 라벨·관계 허용 목록 · 관계 방향(from/to 라벨) · 필수 속성 · evidence_span 원문 존재(본문 · 제목, 공백 · 말줄임 허용 — B.42)
   · 엔티티 키 해석(별칭 사전 — 정확 · 공백 무시 · 포함 일치).
3) 통과분만 document.extraction 에 저장 → 투영 시 MERGE. 실패분은 ops.extraction_issue(검토 대기).
LLM 을 쓸 수 없으면 별칭 사전 기반 규칙 추출로 폴백한다(extracted_by='rule').
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.llm import LlmError, LlmUnavailable, chat, parse_json, resolve
from nhdip.models import ExtractionIssue, OntologySchema, source

WS = re.compile(r"\s+")
# 근거 문장 대조용 정규화 — PDF 추출의 띄어쓰기 · 따옴표 · 가운뎃점 표기 차이는 같은 글자로 본다 (B.42)
_PUNCT = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "ㆍ": "·", "•": "·", "‧": "·", "∙": "·", "－": "-", "–": "-", "—": "-"})
_ELLIPSIS = re.compile(r"\s*(?:…|\.{3,})\s*")


def _norm(s: str) -> str:
    return WS.sub(" ", s or "").strip()


def _compact(s: str) -> str:
    """공백을 모두 지우고 따옴표 · 가운뎃점 표기를 맞춘 비교용 문자열."""
    return WS.sub("", (s or "").translate(_PUNCT)).lower()


def _in_text(span: str, text_c: str) -> bool:
    """근거 문장이 원문(비교용 문자열)에 있는가 — 말줄임(… · ...)으로 이은 조각은 순서대로 모두 있어야 한다."""
    parts = [_compact(p) for p in _ELLIPSIS.split(span or "")]
    parts = [p for p in parts if p]
    if not parts or (len(parts) > 1 and any(len(p) < 4 for p in parts)):
        return False  # 짧은 조각만 이어 붙인 근거는 원문 인용으로 보지 않는다
    pos = 0
    for p in parts:
        i = text_c.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def span_source(span: str, text: str, title: str = "") -> str | None:
    """근거 문장의 출처 — 'body'(청크 본문) · 'title'(문서 제목, 추출 입력에 함께 준다) · None(원문에 없음)."""
    if not span or not span.strip():
        return None
    if _in_text(span, _compact(text)):
        return "body"
    if title and _in_text(span, _compact(title)):
        return "title"
    return None


class Resolver:
    """별칭 사전 기반 엔티티 링크 — {label: {canonical_key: [aliases]}}

    해석 순서(B.42): ① 별칭 정확 일치(공백 정규화) ② 공백 무시 일치('소기업모형' = '소기업 모형')
    ③ 이름 안에 별칭이 들어 있으면 그 별칭의 키('서민금융 공급 확대' → 포용금융). 들어 있는 별칭들이 서로 다른 키를
    가리키면(복합 이름 '가계부채 관리 및 포용금융') 해석하지 않고 검토 대기로 둔다.
    """

    CONTAINS_MIN = 2  # 포함 일치에 쓰는 별칭 최소 글자 수(공백 제외)

    def __init__(self, schema: OntologySchema):
        self.classes = {c["label"]: c for c in schema.classes}
        self.rels = {r["type"]: r for r in schema.relations}
        self.alias: dict[str, dict[str, str]] = {}
        self.compact: dict[str, dict[str, set[str]]] = {}
        for label, entries in (schema.aliases or {}).items():
            m: dict[str, str] = {}
            c: dict[str, set[str]] = {}
            for key, aliases in entries.items():
                for a in [key, *aliases]:
                    m[_norm(a).lower()] = key
                    if _compact(a):
                        c.setdefault(_compact(a), set()).add(key)
            self.alias[label] = m
            self.compact[label] = c

    def match(self, label: str, raw: str) -> str | None:
        """별칭 사전으로만 해석(마스터 여부와 무관) — 없으면 None."""
        m = self.alias.get(label) or {}
        hit = m.get(_norm(raw).lower())
        if hit:
            return hit
        c = self.compact.get(label) or {}
        rc = _compact(raw)
        if not rc:
            return None
        keys = c.get(rc)
        if keys and len(keys) == 1:
            return next(iter(keys))
        found = [a for a in c if len(a) >= self.CONTAINS_MIN and a in rc]
        # 더 긴 일치 별칭의 일부인 별칭은 뺀다('비외감' 안의 '외감'). 남은 별칭이 서로 다른 키면 복합 이름 → 해석하지 않음
        found = [a for a in found if not any(a != b and a in b for b in found)]
        cands = set().union(*(c[a] for a in found)) if found else set()
        return next(iter(cands)) if len(cands) == 1 else None

    def resolve(self, label: str, raw: str) -> str | None:
        cls = self.classes.get(label, {})
        hit = self.match(label, raw) if raw else None
        if hit:
            return hit
        return raw if cls.get("resolve") != "master" and raw else None


def schema_prompt(schema: OntologySchema, top_aliases: int = 30) -> str:
    classes = [f"- {c['label']}: {c.get('description', '')} (key={c.get('key_hint', 'name')})" for c in schema.classes if c.get("extractable", True)]
    rels = [f"- {r['type']}: {r['from']} → {r['to']}" + (f" props={r.get('props')}" if r.get("props") else "") for r in schema.relations if r.get("extractable", True)]
    aliases = {label: list(entries.keys())[:top_aliases] for label, entries in (schema.aliases or {}).items()}
    return "허용 클래스:\n" + "\n".join(classes) + "\n\n허용 관계 (from 이 '$doc' 이면 이 문서 자신):\n" + "\n".join(rels) + "\n\n마스터 키(가능하면 이 키로 지정):\n" + json.dumps(aliases, ensure_ascii=False)


def validate(schema: OntologySchema, resolver: Resolver, chunk_text: str, data: Any, title: str = "") -> tuple[list[dict], list[dict], list[dict]]:
    """(entities, relations, issues)

    근거 문장(evidence_span)은 청크 본문에서 찾고, 없으면 문서 제목에서 찾는다 — 추출 입력에 제목을 함께 주므로
    제목 인용은 정당한 근거다(B.42). 제목에서 찾은 근거는 `span_source: "title"` 로 남긴다.
    """
    ents_ok: list[dict] = []
    rels_ok: list[dict] = []
    issues: list[dict] = []
    if not isinstance(data, dict):
        return [], [], [{"kind": "parse_error", "reason": "JSON 객체가 아님", "raw": data}]
    keymap: dict[str, tuple[str, str]] = {}
    for e in data.get("entities") or []:
        if not isinstance(e, dict):
            issues.append({"kind": "schema_violation", "reason": "엔티티가 객체가 아님", "raw": e})
            continue
        label, span = e.get("label"), e.get("evidence_span") or ""
        raw_key, raw_name = str(e.get("key") or e.get("name") or ""), str(e.get("name") or "")
        if label not in resolver.classes or not resolver.classes[label].get("extractable", True):
            issues.append({"kind": "schema_violation", "reason": f"허용되지 않은 클래스: {label}", "raw": e})
            continue
        src = span_source(span, chunk_text, title)
        if not src:
            issues.append({"kind": "span_not_found", "reason": "evidence_span 이 원문(본문 · 제목)에 없음", "raw": e})
            continue
        # key 로 안 풀리면 name 으로 — 모델이 key 에 설명형 이름을, name 에 별칭을 넣는 경우가 있다
        key = resolver.resolve(label, raw_key) or (resolver.match(label, raw_name) if raw_name and raw_name != raw_key else None)
        extra = {"span_source": "title"} if src == "title" else {}
        if not key:
            issues.append({"kind": "unresolved_entity", "reason": f"마스터에 없는 {label}: {raw_key}", "raw": e})
            ents_ok.append({"label": "Candidate", "key": f"{label}:{raw_key}", "name": raw_key, "props": {"raw_label": label, "reason": "unresolved"}, "evidence_span": span, **extra})
            continue
        for req in resolver.classes[label].get("required", []):
            if req not in (e.get("props") or {}) and req not in ("key", "name"):
                issues.append({"kind": "schema_violation", "reason": f"{label} 필수 속성 누락: {req}", "raw": e})
                break
        else:
            ents_ok.append({"label": label, "key": key, "name": e.get("name") or key, "props": e.get("props") or {}, "evidence_span": span, **extra})
            keymap[raw_key] = (label, key)
            keymap[key] = (label, key)
            if raw_name:
                keymap.setdefault(raw_name, (label, key))
    for r in data.get("relations") or []:
        if not isinstance(r, dict):
            issues.append({"kind": "schema_violation", "reason": "관계가 객체가 아님", "raw": r})
            continue
        rtype = r.get("type")
        spec = resolver.rels.get(rtype)
        if not spec or not spec.get("extractable", True):
            issues.append({"kind": "schema_violation", "reason": f"허용되지 않은 관계: {rtype}", "raw": r})
            continue
        span = r.get("evidence_span") or ""
        rsrc = span_source(span, chunk_text, title) if span else "body"
        if not rsrc:
            issues.append({"kind": "span_not_found", "reason": "관계 evidence_span 이 원문(본문 · 제목)에 없음", "raw": r})
            continue
        def end(v: Any, allowed: str | None = None) -> tuple[str, str] | None:
            # 양끝은 키 문자열 또는 {key, label}(모델에 따라 객체로 답함 — B.40) — 엔티티 목록에 없으면 별칭 사전으로 해석.
            # 라벨이 없으면 관계 정의의 허용 라벨(예: STATES_STANCE → PolicyTheme)로 해석한다(B.42).
            if isinstance(v, dict):
                raw, lab = str(v.get("key") or v.get("name") or ""), v.get("label")
            else:
                raw, lab = str(v or ""), None
            if raw in keymap:
                return keymap[raw]
            if not lab and allowed and allowed != "*":
                lab = allowed
            if lab and lab in resolver.classes:
                k = resolver.resolve(lab, raw)
                return (lab, k) if k else None
            return None

        frm_raw = r.get("from")
        frm = "$doc" if (frm_raw.get("key") if isinstance(frm_raw, dict) else str(frm_raw)) in ("$doc", "doc", "document") else end(frm_raw, spec.get("from") if spec.get("from") != "Document" else None)
        to = end(r.get("to"), spec.get("to"))
        if not to or (frm != "$doc" and not frm):
            issues.append({"kind": "unresolved_entity", "reason": "관계 양끝 엔티티를 해석하지 못함", "raw": r})
            continue
        from_label = "Document" if frm == "$doc" else frm[0]
        if spec["from"] not in (from_label, "*") or spec["to"] not in (to[0], "*"):
            issues.append({"kind": "schema_violation", "reason": f"{rtype} 방향 위반: {from_label}→{to[0]} (허용 {spec['from']}→{spec['to']})", "raw": r})
            continue
        props = {k: v for k, v in (r.get("props") or {}).items() if k in (spec.get("props") or [])}
        allowed_values = spec.get("allowed") or {}
        if any(k in allowed_values and v not in allowed_values[k] for k, v in props.items()):
            issues.append({"kind": "schema_violation", "reason": f"{rtype} 속성값 허용 외: {props}", "raw": r})
            continue
        rels_ok.append({"type": rtype, "from": "$doc" if frm == "$doc" else frm[1], "from_label": from_label, "to": to[1], "to_label": to[0], "props": props, "evidence_span": span, **({"span_source": "title"} if rsrc == "title" else {})})
    return ents_ok, rels_ok, issues


def rule_extract(schema: OntologySchema, resolver: Resolver, text: str, doc_class: str) -> tuple[list[dict], list[dict]]:
    """별칭 사전 매칭 + 기조 키워드 규칙 (LLM 미사용 폴백)."""
    ents: dict[tuple[str, str], dict] = {}
    rels: list[dict] = []
    t = _norm(text)
    stance_cfg = next((r for r in schema.relations if r["type"] == "STATES_STANCE"), {})
    keywords: dict[str, list[str]] = stance_cfg.get("rule_keywords") or {}
    sentences = re.split(r"(?<=[.!?。])\s+|\n", text)
    for label, amap in resolver.alias.items():
        for alias, key in amap.items():
            if len(alias) < 2 or alias not in t.lower():
                continue
            idx = t.lower().find(alias)
            span = t[idx : idx + len(alias)]
            ents.setdefault((label, key), {"label": label, "key": key, "name": key, "props": {}, "evidence_span": span})
    for (label, key), _ in ents.items():
        rels.append({"type": "MENTIONS", "from": "$doc", "from_label": "Document", "to": key, "to_label": label, "props": {}})
        if label == "PolicyTheme" and doc_class in ("gov_policy", "mgmt_decision") and keywords:
            for s in sentences:
                low = s.lower()
                if not any(a in low for a, k in resolver.alias.get(label, {}).items() if k == key):
                    continue
                direction = next((d for d, kws in keywords.items() if any(kw in s for kw in kws)), None)
                if direction:
                    rels.append({"type": "STATES_STANCE", "from": "$doc", "from_label": "Document", "to": key, "to_label": label, "props": {"direction": direction}, "evidence_span": _norm(s)[:200]})
                    break
    return list(ents.values()), rels


def extract_document(session: Session, origin: str, doc, *, agent_code: str = "ontology_extractor", max_chunks: int = 12, workflow_run_id: str | None = None, node_run_id: str | None = None) -> dict[str, Any]:
    from nhdip.graph.projection import active_schema

    schema = active_schema(session)
    if not schema:
        return {"status": "skipped", "reason": "no active schema"}
    resolver = Resolver(schema)
    t = source(origin)
    chunks = session.execute(select(t.chunk).where(t.chunk.document_id == doc.id).order_by(t.chunk.seq).limit(max_chunks)).scalars().all()
    entities: list[dict] = []
    relations: list[dict] = []
    issues_n = 0
    by = "rule"
    mode = "rule"
    llm_failures = 0
    fallback_reason = ""
    try:
        cfg = resolve(session, agent_code)
        mode = "llm"
    except LlmUnavailable as exc:
        fallback_reason = str(exc)
    if mode == "llm":
        by = f"llm:{cfg.model}"
        sys_prompt = cfg.system_prompt or "You extract ontology entities and relations from Korean banking documents. Output JSON only."
        for ch in chunks:
            user = (cfg.user_template or "{schema}\n\n문서 분류: {doc_class}\n제목: {title}\n\n본문:\n{text}\n\n출력 JSON: {{\"entities\":[{{\"label\",\"key\",\"name\",\"props\",\"evidence_span\"}}],\"relations\":[{{\"type\",\"from\",\"to\",\"props\",\"evidence_span\"}}]}}").format(
                schema=schema_prompt(schema), doc_class=doc.doc_class, title=doc.title, text=ch.text
            )
            try:
                res = chat(session, cfg, [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}], json_mode=True, workflow_run_id=workflow_run_id, node_run_id=node_run_id, purpose="extraction")
                data = parse_json(res.text)
            except (LlmError, ValueError) as exc:
                session.add(ExtractionIssue(origin=origin, document_id=doc.id, chunk_id=ch.id, kind="llm_error", reason=str(exc)[:500]))
                issues_n += 1
                llm_failures += 1
                continue
            e_ok, r_ok, issues = validate(schema, resolver, ch.text, data, title=doc.title or "")
            for e in e_ok:
                e["page"] = ch.page
            entities += e_ok
            relations += r_ok
            for i in issues:
                session.add(ExtractionIssue(origin=origin, document_id=doc.id, chunk_id=ch.id, kind=i["kind"], reason=i["reason"], raw=i.get("raw")))
            issues_n += len(issues)
        if chunks and llm_failures == len(chunks):
            # 모든 청크에서 LLM 호출이 실패하면(키·모델 오류 등) 규칙 추출로 폴백 — 그래프에서 문서 근거가 사라지지 않게
            mode, by = "rule", "rule"
            fallback_reason = f"LLM 호출 실패 {llm_failures}건 → 규칙 추출"
    if mode == "rule":
        entities, relations = rule_extract(schema, resolver, doc.text, doc.doc_class)
    # 중복 제거
    seen = set()
    uniq_e = []
    for e in entities:
        k = (e["label"], e["key"])
        if k not in seen:
            seen.add(k)
            uniq_e.append(e)
    seen_r = set()
    uniq_r = []
    for r in relations:
        k = (r["type"], r["from"], r["to"], json.dumps(r.get("props") or {}, sort_keys=True))
        if k not in seen_r:
            seen_r.add(k)
            uniq_r.append(r)
    if mode == "llm" and not any(r["type"] == "MENTIONS" for r in uniq_r):
        uniq_r += [{"type": "MENTIONS", "from": "$doc", "from_label": "Document", "to": e["key"], "to_label": e["label"], "props": {}} for e in uniq_e if e["label"] != "Candidate"]
    doc.extraction = {"by": by, "schema_version": schema.version, "entities": uniq_e, "relations": uniq_r, "issues": issues_n, **({"fallback_reason": fallback_reason} if mode == "rule" else {})}
    doc.status = "extracted" if issues_n == 0 else "partial"
    return {"document": doc.doc_code, "origin": origin, "by": by, "entities": len(uniq_e), "relations": len(uniq_r), "issues": issues_n}
