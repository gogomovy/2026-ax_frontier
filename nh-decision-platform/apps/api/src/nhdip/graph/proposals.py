"""온톨로지 변경 제안 — 만들기 · 영향 · 승인(적용) · 반려 (Phase M · ONB-09 · Q181)

에이전트(구축 워크플로) · 관리자 · 추출 검토의 스키마 변경은 연산 목록(`graph.schema.apply_ops`)으로 된 제안이 된다.
승인하면 활성 스키마에 연산을 적용 → 검증(ONB-03) → 새 판 활성 → `ontology.changed`(그래프 재투영 · 재추출).
같은 연산이 대기 중 제안에 이미 있거나 활성 스키마에 이미 반영돼 있으면 새로 만들지 않는다.
"""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.events import emit
from nhdip.models import OntologyProposal, OntologySchema, Setting, utcnow

from .schema import apply_ops, as_dict, diff_schema, op_key, validate_schema

DEFAULT_BUILD = {
    "enabled": True,
    "llm": True,  # 구조 파악 의미 · 객체 유형 이름 · 링크 이름 · 애매한 해소에 LLM 을 쓴다(Q182 — 1차 판단은 결정론)
    "max_datasets": 8,  # 한 번 실행에서 구조를 파악할 데이터셋 수
    "auto_apply": [],  # 자동 적용할 연산 종류(예: ["add_alias"]) — 기본 없음(Q181)
    "min_confidence": 0.9,  # 자동 적용 신뢰도 기준
    "link_min_containment": 0.95,  # 외래 키 후보 — 값의 몇 % 가 상대 기본 키에 있어야 하는지
    "link_min_distinct": 2,  # 외래 키 후보 열의 최소 고유값 수
    "resolve_min_score": 0.84,  # 개체 해소 — 이 점수 이상이면 별칭 제안
    "resolve_llm_band": [0.7, 0.84],  # 이 구간은 LLM 판정(LLM 없으면 제안하지 않음)
    "reextract_per_run": 5,  # 스키마 판이 바뀌었을 때 실행당 다시 추출할 문서 수(ONB-11)
    "steward_review": True,  # 한 부서 자료만 닿는 제안은 그 부서 데이터 책임자도 승인(§40 STW-07) — 끄면 관리자만
}


def build_policy(session: Session) -> dict[str, Any]:
    st = session.get(Setting, "ontology.build")
    raw = st.value if st is not None and isinstance(st.value, dict) else {}
    out = dict(DEFAULT_BUILD)
    for k, v in raw.items():
        if k in out and isinstance(v, type(out[k])) or (k in out and isinstance(out[k], float) and isinstance(v, (int, float))):
            out[k] = v
    return out


def active(session: Session) -> OntologySchema | None:
    return session.execute(select(OntologySchema).where(OntologySchema.active).order_by(OntologySchema.version.desc())).scalars().first()


def activate_schema(session: Session, schema: dict[str, Any], *, note: str, actor: str | None) -> int:
    """새 판으로 저장하고 활성화 — `ontology.changed` 를 낸다(그래프 투영 · 추출이 깨어남). 검증은 호출자가 한다."""
    s = as_dict(schema)
    last = session.execute(select(func.max(OntologySchema.version))).scalar() or 0
    for row in session.execute(select(OntologySchema).where(OntologySchema.active)).scalars():
        row.active = False
    session.add(OntologySchema(version=last + 1, classes=s["classes"], relations=s["relations"], aliases=s["aliases"], interfaces=s["interfaces"], note=(note or "")[:500], active=True))
    session.flush()
    emit(session, "ontology.changed", {"version": last + 1, "note": (note or "")[:120]}, actor or "system")
    return last + 1


def _ns(schema: dict[str, Any], version: int) -> SimpleNamespace:
    return SimpleNamespace(version=version, classes=schema["classes"], relations=schema["relations"], aliases=schema["aliases"], interfaces=schema["interfaces"])


def estimate_impact(session: Session, base: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    """적용하면 그래프가 어떻게 바뀌는지 — 원장에서 같은 규칙으로 모아 클래스별 개체 수 · 관계 유형별 수를 비교(Neo4j 불필요)."""
    from .projection import collect_graph

    try:
        b0 = collect_graph(session, _ns(base, 0))
        b1 = collect_graph(session, _ns(proposed, 0))
    except Exception as exc:  # noqa: BLE001 — 영향 계산 실패가 제안을 막지 않는다
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    def counts(b: Any) -> tuple[Counter, Counter]:
        nodes: Counter = Counter()
        for labels, items in b.nodes.items():
            nodes[labels[0]] += len(items)
        rels: Counter = Counter()
        for (rtype, _, _), items in b.rels.items():
            rels[rtype] += len(items)
        return nodes, rels

    n0, r0 = counts(b0)
    n1, r1 = counts(b1)
    nodes = {k: {"before": n0.get(k, 0), "after": n1.get(k, 0)} for k in sorted(set(n0) | set(n1)) if n0.get(k, 0) != n1.get(k, 0)}
    rels = {k: {"before": r0.get(k, 0), "after": r1.get(k, 0)} for k in sorted(set(r0) | set(r1)) if r0.get(k, 0) != r1.get(k, 0)}
    dangling = {k: v for k, v in b1.dangling().items() if v != b0.dangling().get(k, 0)}
    return {"nodes": nodes, "relations": rels, "dangling": dangling, "nodesDelta": sum(n1.values()) - sum(n0.values()), "relationsDelta": sum(r1.values()) - sum(r0.values())}


def op_datasets(op: dict[str, Any]) -> set[str] | None:
    """연산이 읽는 원천 자료(코드 또는 이름) — 원천이 없는 연산(별칭 · 수정 · 속성)은 None."""
    kind = op.get("op")
    if kind == "add_class":
        backing = (op.get("class") or {}).get("backing") or []
    elif kind in ("add_backing", "add_link_backing"):
        backing = [op.get("backing") or {}]
    elif kind == "add_relation":
        backing = (op.get("relation") or {}).get("backing") or []
    else:
        return None
    out = {str(b["dataset"]) for b in backing if isinstance(b, dict) and b.get("dataset")}
    return out or None


def proposal_datasets(ops: list[dict[str, Any]]) -> tuple[set[str], bool]:
    """(제안이 닿는 원천 자료, 자료로 가를 수 없는 연산이 있는가). 속성 추가는 같은 제안에서 그 클래스에 원천을 붙이는 연산의 자료로 본다.
    가를 수 없는 연산(별칭 · 클래스 · 관계 수정 · 원천 없는 속성)이 하나라도 있으면 전행 영향 — 관리자 몫."""
    by_label: dict[str, set[str]] = {}
    for o in ops:
        label = (o.get("class") or {}).get("label") if o.get("op") == "add_class" else o.get("label") if o.get("op") == "add_backing" else None
        ds = op_datasets(o) if label else None
        if label and ds:
            by_label.setdefault(str(label), set()).update(ds)
    out: set[str] = set()
    loose = False
    for o in ops:
        if not isinstance(o, dict):
            continue
        ds = op_datasets(o)
        if ds is None and o.get("op") == "add_property":
            ds = by_label.get(str(o.get("label") or "")) or None
        if ds is None:
            loose = True
        else:
            out |= ds
    return out, loose


def pending_keys(session: Session) -> set[str]:
    keys: set[str] = set()
    for p in session.execute(select(OntologyProposal).where(OntologyProposal.status == "pending")).scalars():
        keys |= {op_key(o) for o in p.ops or [] if isinstance(o, dict)}
    return keys


def rejected_keys(session: Session) -> set[str]:
    """관리자가 반려한 제안의 연산 — 구축 에이전트가 같은 연산을 매 실행 다시 제안하지 않게(반려 사유가 남는다).
    다시 제안받으려면 관리자가 [변경 제안]에서 그 제안을 '다시 검토'(반려 취소)한다."""
    keys: set[str] = set()
    for p in session.execute(select(OntologyProposal).where(OntologyProposal.status == "rejected")).scalars():
        keys |= {op_key(o) for o in p.ops or [] if isinstance(o, dict)}
    return keys


def create_proposal(session: Session, ops: list[dict[str, Any]], *, title: str, summary: str = "", source: str = "agent", agent_code: str | None = None,
                    workflow_run_id: str | None = None, evidence: dict[str, Any] | None = None, actor: str | None = None, with_impact: bool = True) -> OntologyProposal | None:
    """새 제안 — 대기 중 제안 · 활성 스키마와 겹치는 연산은 뺀다(에이전트 제안은 반려된 연산도 뺀다). 남는 연산이 없으면 None."""
    sc = active(session)
    if sc is None:
        return None
    base = as_dict(sc)
    taken = pending_keys(session) | (rejected_keys(session) if source == "agent" else set())
    fresh = [o for o in ops if isinstance(o, dict) and op_key(o) not in taken]
    # 이미 반영된 연산(적용해도 바뀌지 않음)은 뺀다
    proposed, applied, skipped = apply_ops(base, fresh)
    if not applied:
        return None
    check = validate_schema(proposed, session)
    p = OntologyProposal(
        status="pending" if not check["errors"] else "failed", source=source, agent_code=agent_code, workflow_run_id=workflow_run_id, title=title[:200], summary=summary,
        ops=applied, evidence=evidence or {}, impact=estimate_impact(session, base, proposed) if with_impact and not check["errors"] else {},
        validation={**check, "skipped": [{"key": op_key(x["op"]), "reason": x["reason"]} for x in skipped][:50], "diff": diff_schema(base, proposed)},
        base_version=sc.version, created_by=actor,
    )
    session.add(p)
    session.flush()
    return p


def decide(session: Session, p: OntologyProposal, *, approve: bool, actor: str, drop: list[int] | None = None, note: str | None = None) -> dict[str, Any]:
    """승인(= 적용) · 반려. drop = 빼고 적용할 연산 순번. 적용 검증에 실패하면 status=failed 로 남기고 오류를 돌려준다."""
    if p.status != "pending":
        return {"ok": False, "error": f"대기 중인 제안이 아닙니다({p.status})"}
    p.decided_by, p.decided_at, p.note = actor, utcnow(), (note or None)
    if not approve:
        p.status = "rejected"
        return {"ok": True, "status": "rejected"}
    ops = [o for i, o in enumerate(p.ops or []) if i not in set(drop or [])]
    sc = active(session)
    if sc is None:
        return {"ok": False, "error": "활성 스키마가 없습니다"}
    proposed, applied, skipped = apply_ops(as_dict(sc), ops)
    if not applied:
        p.status = "superseded"
        p.validation = {**(p.validation or {}), "skipped": [{"key": op_key(x["op"]), "reason": x["reason"]} for x in skipped][:50]}
        return {"ok": True, "status": "superseded", "reason": "적용할 변경이 남아 있지 않습니다(이미 반영됨)"}
    check = validate_schema(proposed, session)
    if check["errors"]:
        p.status = "failed"
        p.validation = {**(p.validation or {}), **check}
        return {"ok": False, "status": "failed", "error": " · ".join(check["errors"][:6])}
    v = activate_schema(session, proposed, note=f"제안 #{p.id} 적용 — {p.title}"[:200], actor=actor)
    p.status, p.applied_version, p.ops = "applied", v, applied
    return {"ok": True, "status": "applied", "version": v, "applied": len(applied), "skipped": len(skipped), "warnings": check["warnings"]}


def reopen(session: Session, p: OntologyProposal, *, actor: str) -> dict[str, Any]:
    """반려 취소 — 다시 승인 대기로(반려 기록은 note 에 남긴다). 그 사이 같은 연산이 다른 제안으로 대기 중이면 거절."""
    if p.status != "rejected":
        return {"ok": False, "error": f"반려된 제안만 다시 검토할 수 있습니다({p.status})"}
    mine = {op_key(o) for o in p.ops or [] if isinstance(o, dict)}
    if mine & pending_keys(session):
        return {"ok": False, "error": "같은 변경이 다른 제안으로 승인 대기 중입니다"}
    prev = f"반려({p.decided_by} · {p.decided_at.isoformat() if p.decided_at else '-'}): {p.note or ''}"
    p.status, p.note, p.decided_by, p.decided_at = "pending", f"{prev} → {actor} 가 다시 검토"[:1000], None, None
    return {"ok": True, "status": "pending"}


def auto_apply(session: Session, p: OntologyProposal, policy: dict[str, Any]) -> dict[str, Any] | None:
    """정책이 허용한 연산 종류 · 신뢰도만 있는 제안이면 시스템이 승인한다(기본 꺼짐 — Q181)."""
    kinds = set(policy.get("auto_apply") or [])
    if not kinds or p.status != "pending":
        return None
    conf = float((p.evidence or {}).get("minConfidence", 0) or 0)
    if all(o.get("op") in kinds for o in p.ops or []) and conf >= float(policy.get("min_confidence", 0.9)):
        return decide(session, p, approve=True, actor="system:auto", note=f"자동 적용(설정 ontology.build.auto_apply · 신뢰도 {conf:.2f})")
    return None


def proposal_json(p: OntologyProposal) -> dict[str, Any]:
    def iso(v: Any) -> str | None:
        return v.isoformat() if v is not None else None

    return {"id": p.id, "status": p.status, "source": p.source, "agent": p.agent_code, "run": p.workflow_run_id, "title": p.title, "summary": p.summary,
            "ops": p.ops or [], "opKeys": [op_key(o) for o in p.ops or []], "evidence": p.evidence or {}, "impact": p.impact or {}, "validation": p.validation or {},
            "baseVersion": p.base_version, "appliedVersion": p.applied_version, "createdBy": p.created_by, "createdAt": iso(p.created_at),
            "decidedBy": p.decided_by, "decidedAt": iso(p.decided_at), "note": p.note}
