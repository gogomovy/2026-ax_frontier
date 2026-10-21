"""부서 데이터 책임자 승인함 (요구사항 §40 STW) — 에이전트가 새 자료로 만든 제안과 부서 사용자의 분석 요청을, 그 자료 · 요청이 속한
부서의 데이터 책임자(또는 관리자)가 승인하면 반영한다. 승인 전에는 계산 · 화면 · 그래프 어디에도 나가지 않는다.

  종류       만드는 곳                                         승인하면
  analysis   분석 제안 에이전트(propose_analysis)              분석 에이전트(지표 · 흐름 · 보고서 탭) 생성 → 첫 실행 → 화면 · 검색 색인 · 그래프
             · 사용자 분석 요청([분석 에이전트 만들기])
  metric     지표 제안 에이전트(propose_metrics)               지표 켜기 → 계산 커널 계산 · 지표 이력
  concept    개념 연결 에이전트(propose_concepts)              자료 → 업무 개념(DESCRIBES) 연결 → 그래프 재투영 · 설명 카드 개념 태그
  ontology   온톨로지 구축 에이전트(propose_ontology)          스키마 변경(객체 유형 · 원천 연결 · 속성 · 링크) 적용 → 새 판 → 그래프 재투영 · 재추출

범위 — 자료의 현재 판 소유 조직이 모두 책임자 부서(그 아래 조직 포함) 안이면 그 부서 자료다. 소유가 없는 판(전행 공통) · 공통 통합 DB 는 관리자만.
온톨로지 변경은 연산이 닿는 원천 자료가 모두 그 부서 자료일 때만(별칭 · 수정 · 여러 부서 · 전행 자료가 섞이면 관리자 — 설정 ontology.build.steward_review).
링크는 양 끝 객체 유형의 원천 자료까지 본다 — 다른 부서 자료로 만든 객체 유형으로 잇는 링크는 관리자(또는 양쪽을 소유한 책임자).
사용자 분석 요청은 요청자 소속이 책임자 부서 안이면. 본인이 요청한 것은 승인 · 반려할 수 없다(4-eyes).
HTTP 를 모른다 — 호출한 쪽(api.steward_proposals · api.admin_data)이 권한 · 감사 · 커밋을 맡는다.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.events import emit
from nhdip.models import AnalysisAgent, AnalysisAgentVersion, AppUser, Dataset, Metric, OntologyProposal, OrgUnit, Screen, ScreenGrant, Setting, utcnow

AUTO_ACTOR = "agent:analysis_proposer"  # 분석 제안 에이전트가 낸 요청의 요청자(사람이 아님 — 4-eyes 대상 아님)
PROPOSED_CONCEPTS = "proposed_concepts"  # 자료 정의 mapping 안의 개념 연결 제안(승인 대기)
REJECTED_CONCEPTS = "rejected_concepts"  # 사람이 반려한 연결(다시 제안하지 않음)
SKIPPED_CONCEPTS = "skipped_concepts"  # 에이전트가 관련 없다고 본 후보(다시 묻지 않음 · 화면에 보이지 않음)
KINDS = ("analysis", "metric", "concept", "ontology")
STATUSES = ("pending", "approved", "rejected")
ONTO_STATUS = {"pending": "pending", "applied": "approved", "rejected": "rejected"}  # 온톨로지 제안 상태 → 승인함 상태(실패 · 대체됨은 관리자 화면)


class StewardError(Exception):
    """승인함 오류 — status 는 HTTP 상태로 옮긴다(404 없음 · 409 상태 충돌 · 422 입력)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Viewer:
    """승인함을 보는 사람 — 관리자는 전체, 책임자는 자기 부서 범위."""

    emp_no: str
    admin: bool
    scope: OrgUnit | None = None
    orgs: set[str] = field(default_factory=set)

    def scope_json(self) -> dict[str, Any] | None:
        if self.admin:
            return {"code": None, "name": "전체(관리자)"}
        return {"code": self.scope.code, "name": self.scope.name} if self.scope is not None else None


# ═════════════════════════ 범위 · 소유 ═════════════════════════
def scope_orgs(session: Session, user: Any) -> tuple[OrgUnit | None, set[str]]:
    """책임자 부서(가장 가까운 부 · 지역본부)와 그 아래 조직 코드 전체."""
    from nhdip.analysis_agents.team import subtree
    from nhdip.orgs import steward_scope

    scope = steward_scope(session, user.org_code) if getattr(user, "org_code", None) else None
    if scope is None:
        return None, set()
    return scope, subtree(session, scope.code)


def viewer_of(session: Session, user: Any) -> Viewer | None:
    """승인함을 볼 수 있으면 Viewer, 아니면 None(관리자도 책임자도 아님)."""
    admin = getattr(user, "role", None) == "admin"
    steward = bool(getattr(user, "data_steward", False))
    if not admin and not steward:
        return None
    scope, orgs = scope_orgs(session, user) if steward else (None, set())
    return Viewer(user.emp_no, admin, scope, orgs)


def dataset_owners(session: Session, ds: Dataset) -> tuple[set[str], bool]:
    """(현재 판 소유 조직, 소유 없는 판이 있는가). 공통 통합 DB 는 소유 없음(전행)으로 본다."""
    if getattr(ds, "common", False):
        return set(), True
    from nhdip.data.datasets import current_versions

    owners: set[str] = set()
    unowned = False
    for v in current_versions(session, ds):
        if v.owner_org:
            owners.add(v.owner_org)
        else:
            unowned = True
    return owners, unowned


def owns(owners: set[str], unowned: bool, orgs: set[str]) -> bool:
    """부서 범위가 그 자료를 온전히 소유하는가 — 판이 하나라도 다른 부서 · 전행이면 관리자 몫."""
    return bool(owners) and not unowned and owners <= orgs


def can_review_dataset(session: Session, viewer: Viewer, ds: Dataset | None) -> bool:
    if viewer.admin:
        return True  # 관리자는 자료를 찾지 못한 제안(정의가 지워짐 등)도 본다
    if ds is None:
        return False
    owners, unowned = dataset_owners(session, ds)
    return owns(owners, unowned, viewer.orgs)


def owner_org_of(session: Session, ds: Dataset) -> str | None:
    """자동 제안의 소유 조직 — 현재 판이 한 부서 소유일 때 그 조직(여럿이면 첫 조직, 같은 부서면 팀이 같다). 전행이 섞이면 None(관리자)."""
    owners, unowned = dataset_owners(session, ds)
    return sorted(owners)[0] if owners and not unowned else None


# ═════════════════════════ 분석 공간 고르기 ═════════════════════════
def org_resources(session: Session, org_code: str) -> set[str]:
    """그 조직(상위 조직 권한 포함)이 받은 화면의 API 리소스 — api.deps.user_resources 와 같은 규칙(HTTP 계층을 부르지 않게 핵심 계층에 둔다)."""
    from nhdip.orgs import org_chain

    chain = org_chain(session, org_code)
    if not chain:
        return set()
    granted = set(session.execute(select(ScreenGrant.screen_code).where(ScreenGrant.org_code.in_([o.code for o in chain]))).scalars())
    deny = session.get(Setting, "screen.deny_unit_types")
    deny_map: dict[str, list[str]] = deny.value if deny is not None and isinstance(deny.value, dict) else {}
    types = {o.unit_type for o in chain}
    mapping_s = session.get(Setting, "screen.resources")
    mapping: dict[str, list[str]] = mapping_s.value if mapping_s is not None and isinstance(mapping_s.value, dict) else {}
    out: set[str] = set()
    for sc in session.execute(select(Screen).where(Screen.active, Screen.code.in_(granted))).scalars():
        if sc.admin_only or set(deny_map.get(sc.code) or []) & types:
            continue
        out |= set(mapping.get(sc.code) or [])
    return out


def builder_spaces(session: Session) -> dict[str, dict[str, Any]]:
    from nhdip.analysis_registry import spaces

    return {k: sp for k, sp in spaces(session).items() if sp.get("builder")}


def auto_policy(session: Session) -> dict[str, Any]:
    from nhdip.seed.defs_core import SETTINGS

    base = dict(SETTINGS.get("analysis.auto", ({}, ""))[0])
    s = session.get(Setting, "analysis.auto")
    if s is not None and isinstance(s.value, dict):
        base.update(s.value)
    return base


def pick_space(session: Session, owner_org: str | None) -> str | None:
    """자동 분석을 둘 공간 — 설정(analysis.auto.space)이 있으면 그것, 아니면 자료를 올린 팀이 볼 수 있는 첫 분석 공간.
    팀이 볼 수 있는 공간이 없으면 None(제안하지 않음 — 만들어도 그 팀이 결과를 못 본다). 전행 자료는 첫 공간(관리자가 승인 때 바꿀 수 있다)."""
    sps = builder_spaces(session)
    pref = str(auto_policy(session).get("space") or "").strip()
    if pref in sps:
        return pref
    if owner_org:
        res = org_resources(session, owner_org)
        for k, sp in sps.items():
            need = {r for r in (sp.get("tabsResource"), sp.get("resource")) if r}
            if need and need <= res:
                return k
        return None
    return next(iter(sps), None)


# ═════════════════════════ 목록 ═════════════════════════
def _iso(v: Any) -> str | None:
    return v.isoformat() if v else None


def _names(session: Session, emps: set[str]) -> dict[str, str]:
    emps = {e for e in emps if e and not e.startswith("agent:")}
    return dict(session.execute(select(AppUser.emp_no, AppUser.name).where(AppUser.emp_no.in_(emps))).all()) if emps else {}


def _requester_in_scope(session: Session, viewer: Viewer, emp_no: str | None) -> bool:
    if viewer.admin:
        return True
    u = session.get(AppUser, emp_no) if emp_no and not emp_no.startswith("agent:") else None
    return u is not None and bool(u.org_code) and u.org_code in viewer.orgs


def _visible_analysis(session: Session, viewer: Viewer, v: AnalysisAgentVersion) -> bool:
    auto = (v.spec or {}).get("auto") or {}
    if auto.get("dataset"):
        return can_review_dataset(session, viewer, session.get(Dataset, str(auto["dataset"])))
    return _requester_in_scope(session, viewer, v.requested_by)


def _analysis_items(session: Session, viewer: Viewer, status: str) -> list[dict[str, Any]]:
    from nhdip.analysis_registry import space as get_space

    q = select(AnalysisAgentVersion, AnalysisAgent).join(AnalysisAgent, AnalysisAgent.code == AnalysisAgentVersion.agent_code)
    if status:
        q = q.where(AnalysisAgentVersion.status == status)
    rows = session.execute(q.order_by(AnalysisAgentVersion.created_at.desc()).limit(200)).all()
    rows = [(v, a) for v, a in rows if _visible_analysis(session, viewer, v)]
    names = _names(session, {v.requested_by or "" for v, _ in rows} | {v.reviewed_by or "" for v, _ in rows})
    out = []
    for v, a in rows:
        spec = v.spec or {}
        auto = spec.get("auto") or {}
        ds = session.get(Dataset, str(auto["dataset"])) if auto.get("dataset") else None
        sp = get_space(session, a.space) or {}
        pv = v.preview or {}
        out.append({
            "kind": "analysis", "id": f"analysis:{a.code}:{v.version}", "status": v.status, "agent": a.code, "version": v.version,
            "title": spec.get("title") or a.title, "purpose": spec.get("purpose") or "", "auto": bool(auto),
            "dataset": auto.get("dataset"), "datasetName": ds.name if ds is not None else auto.get("datasetName"), "by": auto.get("by"), "periods": auto.get("periods"),
            "space": a.space, "spaceLabel": sp.get("label") or a.space, "spaceLocked": bool(a.version),
            "metrics": [{"key": m.get("key"), "label": m.get("label"), "formula": m.get("formula"), "unit": m.get("unit")} for m in spec.get("metrics") or []][:20],
            "tables": [{"key": t.get("key"), "caption": t.get("caption")} for t in spec.get("tables") or []][:8],
            "schedule": spec.get("schedule"),
            "preview": {"figures": [{"id": k, **f} for k, f in (pv.get("figures") or {}).items()][:20], "opinions": (pv.get("opinions") or [])[:3]},
            "issues": [i.get("message") for i in ((v.validation or {}).get("issues") or [])][:10],
            "sourceText": (v.source_text or "")[:1200],
            "requestedBy": v.requested_by, "requestedByName": "분석 제안 에이전트" if (v.requested_by or "").startswith("agent:") else names.get(v.requested_by or ""),
            "createdAt": _iso(v.created_at), "reviewedBy": v.reviewed_by, "reviewedByName": names.get(v.reviewed_by or ""), "reviewedAt": _iso(v.reviewed_at), "reviewNote": v.review_note,
            "href": (f"{sp.get('path')}/{a.tab_key}" if sp.get("path") else f"/analysis/{a.space}/{a.tab_key}") if a.status in ("active", "paused") and v.status == "approved" else None,
            "canReview": v.status == "pending" and v.requested_by != viewer.emp_no,
        })
    return out


def _metric_status(m: Metric) -> str | None:
    from nhdip.workflow.metric_nodes import APPROVED, PROPOSED, REJECTED

    d = m.description or ""
    if d.startswith(PROPOSED) and not m.enabled:
        return "pending"
    if d.startswith(APPROVED):
        return "approved"
    if d.startswith(REJECTED):
        return "rejected"
    return None


def metric_dataset(session: Session, m: Metric, resolver: Any = None) -> Dataset | None:
    """제안 지표가 읽는 자료(첫 번째) — 지표 입력의 자료 이름 · 코드를 지금 정의로 찾는다."""
    from nhdip.data.sources import Resolver
    from nhdip.graph.projection import _datasets_in_args

    res = resolver or Resolver(session)
    for ref in sorted(_datasets_in_args(m.args)):
        d = res.resolve(ref)
        if d is not None:
            return d
    return None


def _metric_items(session: Session, viewer: Viewer, status: str) -> list[dict[str, Any]]:
    from nhdip.data.sources import Resolver
    from nhdip.workflow.metric_nodes import APPROVED, PROPOSED, REJECTED, WORKFLOW

    rows = [(m, st) for m in session.execute(select(Metric).where(Metric.workflow_code == WORKFLOW).order_by(Metric.code)).scalars()
            if (st := _metric_status(m)) is not None and (not status or st == status)]
    if not rows:
        return []
    res = Resolver(session)  # 자료 찾기는 항목이 있을 때만(사이드바 건수가 매 화면 이동마다 불린다)
    out = []
    for m, st in rows:
        ds = metric_dataset(session, m, res)
        if not can_review_dataset(session, viewer, ds):
            continue
        reason = (m.description or "")
        for p in (PROPOSED, APPROVED, REJECTED):
            reason = reason.removeprefix(p)
        out.append({"kind": "metric", "id": f"metric:{m.code}", "status": st, "code": m.code, "label": m.label, "formula": m.formula, "unit": m.unit,
                    "reason": reason.strip()[:600], "dataset": ds.code if ds else None, "datasetName": ds.name if ds else None, "canReview": st == "pending"})
    return out


def _concept_items(session: Session, viewer: Viewer, status: str, schema_ko: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    keys = {"pending": (PROPOSED_CONCEPTS,), "approved": ("concepts",), "rejected": (REJECTED_CONCEPTS,)}
    wanted = keys.get(status) or (PROPOSED_CONCEPTS, "concepts", REJECTED_CONCEPTS)
    st_of = {PROPOSED_CONCEPTS: "pending", "concepts": "approved", REJECTED_CONCEPTS: "rejected"}
    for ds in session.execute(select(Dataset).where(Dataset.active).order_by(Dataset.code)).scalars():
        m = ds.mapping or {}
        if not any(m.get(k) for k in wanted):
            continue
        if not can_review_dataset(session, viewer, ds):
            continue
        for k in wanted:
            for c in m.get(k) or []:
                if not isinstance(c, dict) or not c.get("label") or not c.get("key"):
                    continue
                if k == "concepts" and not c.get("proposedBy"):
                    continue  # 사람이 정의에 직접 적은 연결은 승인함 기록이 아니다
                out.append({"kind": "concept", "id": f"concept:{ds.code}:{c['label']}:{c['key']}", "status": st_of[k], "dataset": ds.code, "datasetName": ds.name,
                            "label": c["label"], "labelKo": schema_ko.get(c["label"], c["label"]), "key": c["key"], "name": c.get("name") or c["key"],
                            "score": c.get("score"), "evidence": (c.get("evidence") or [])[:5], "reason": c.get("reason"), "by": c.get("by"),
                            "proposedAt": c.get("at"), "decidedBy": c.get("approvedBy") or c.get("rejectedBy"), "decidedAt": c.get("approvedAt") or c.get("rejectedAt"),
                            "note": c.get("note"), "canReview": k == PROPOSED_CONCEPTS})
    return out


def ontology_datasets(session: Session, p: OntologyProposal, resolver: Any = None) -> tuple[list[Dataset], bool]:
    """(제안 연산이 닿는 원천 자료, 부서로 가를 수 없는가) — 원천이 없는 연산이 있거나 자료를 찾지 못하면 가를 수 없다(관리자 몫)."""
    own, linked, loose = ontology_scope(session, p, resolver)
    return own + [d for d in linked if all(x.code != d.code for x in own)], loose


def ontology_scope(session: Session, p: OntologyProposal, resolver: Any = None) -> tuple[list[Dataset], list[Dataset], bool]:
    """(연산의 원천 자료, 링크가 잇는 기존 객체 유형의 원천 자료, 부서로 가를 수 없는가).

    링크 유형은 양 끝 객체 유형이 있어야 뜻이 있다 — 다른 부서 자료로 만든 객체 유형으로 잇는 링크는 그 부서 그래프에도 관계가 생기므로
    양쪽 자료를 모두 소유한 책임자만(아니면 관리자) 승인한다(§40 STW-08). 같은 제안에서 새로 만드는 객체 유형은 그 원천이 이미 연산의 원천이다."""
    from nhdip.data.sources import Resolver
    from nhdip.graph.projection import active_schema
    from nhdip.graph.proposals import proposal_datasets

    res = resolver or Resolver(session)
    ops = [o for o in p.ops or [] if isinstance(o, dict)]
    refs, loose = proposal_datasets(ops)
    created = {str((o.get("class") or {}).get("label")) for o in ops if o.get("op") == "add_class"}
    ends = {str((o.get("relation") or {}).get(k)) for o in ops if o.get("op") == "add_relation" for k in ("from", "to") if (o.get("relation") or {}).get(k)} - created
    linked_refs: set[str] = set()
    if ends:
        sc = active_schema(session)
        for c in (sc.classes if sc is not None else []) or []:
            if c.get("label") in ends:
                linked_refs |= {str(b["dataset"]) for b in c.get("backing") or [] if isinstance(b, dict) and b.get("dataset")}

    def resolve(refs_: set[str]) -> list[Dataset]:
        nonlocal loose
        out: list[Dataset] = []
        for ref in sorted(refs_):
            d = res.resolve(ref)
            if d is None:
                loose = True
            elif all(x.code != d.code for x in out):
                out.append(d)
        return out

    own = resolve(refs)
    linked = [d for d in resolve(linked_refs - refs) if all(x.code != d.code for x in own)]
    return own, linked, loose or not own


def can_review_ontology(session: Session, viewer: Viewer, p: OntologyProposal, resolver: Any = None, policy: dict[str, Any] | None = None) -> bool:
    if viewer.admin:
        return True
    from nhdip.graph.proposals import build_policy

    if not (policy if policy is not None else build_policy(session)).get("steward_review", True):
        return False
    dss, loose = ontology_datasets(session, p, resolver)
    return not loose and all(can_review_dataset(session, viewer, d) for d in dss)


def _ontology_items(session: Session, viewer: Viewer, status: str) -> list[dict[str, Any]]:
    from nhdip.data.sources import Resolver
    from nhdip.graph.proposals import build_policy
    from nhdip.graph.schema import op_key

    wanted = [k for k, v in ONTO_STATUS.items() if not status or v == status]
    rows = list(session.execute(select(OntologyProposal).where(OntologyProposal.status.in_(wanted)).order_by(OntologyProposal.id.desc()).limit(200)).scalars())
    if not rows:
        return []
    pol = build_policy(session)
    if not viewer.admin and not pol.get("steward_review", True):
        return []
    res = Resolver(session)
    scoped = [(p, *ontology_scope(session, p, res)) for p in rows]
    seen = [(p, own, linked, loose) for p, own, linked, loose in scoped
            if viewer.admin or (not loose and all(can_review_dataset(session, viewer, d) for d in own + linked))]
    names = _names(session, {s[0].decided_by or "" for s in seen} | {s[0].created_by or "" for s in seen})
    out = []
    for p, dss, linked, loose in seen:
        ops = [o for o in p.ops or [] if isinstance(o, dict)]
        ev = p.evidence or {}
        # 근거 items 는 자료별 제안(§40 STW-07)부터 연산과 같은 순서 — 이전 제안은 순서가 맞지 않을 수 있어 쓰지 않는다
        why = ev.get("items") if "datasets" in ev and isinstance(ev.get("items"), list) and len(ev["items"]) == len(ops) else None
        imp = p.impact or {}
        out.append({
            "kind": "ontology", "id": f"ontology:{p.id}", "status": ONTO_STATUS[p.status], "pid": p.id, "title": p.title, "summary": p.summary, "source": p.source,
            "datasets": [{"code": d.code, "name": d.name} for d in dss], "scoped": not loose,
            # 링크가 잇는 기존 객체 유형의 원천 — 다른 부서 자료면 그 부서 그래프에도 관계가 생긴다(양쪽 소유 책임자 · 관리자만 승인)
            "linkedDatasets": [{"code": d.code, "name": d.name} for d in linked],
            "ops": [{"op": o, "key": op_key(o), **({k: (why[i] or {}).get(k) for k in ("why", "confidence", "by")} if why else {})} for i, o in enumerate(ops[:80])],
            "opCount": len(ops),
            "impact": {k: imp[k] for k in ("nodes", "relations", "dangling", "nodesDelta", "relationsDelta", "error") if k in imp},
            "warnings": ((p.validation or {}).get("warnings") or [])[:10],
            "baseVersion": p.base_version, "appliedVersion": p.applied_version, "createdAt": _iso(p.created_at),
            "createdBy": p.created_by, "createdByName": names.get(p.created_by or "") or ("온톨로지 구축 에이전트" if p.source == "agent" else None),
            "decidedBy": p.decided_by, "decidedByName": names.get(p.decided_by or "") or ("자동 적용" if (p.decided_by or "").startswith("system:") else None),
            "decidedAt": _iso(p.decided_at), "note": p.note,
            "canReview": p.status == "pending" and p.created_by != viewer.emp_no,
        })
    return out


def _schema_ko(session: Session) -> dict[str, str]:
    from nhdip.graph.projection import active_schema
    from nhdip.graph.schema import CLASS_KO

    sc = active_schema(session)
    out = dict(CLASS_KO)
    for c in (sc.classes if sc is not None else []) or []:
        if c.get("ko"):
            out[c["label"]] = c["ko"]
    return out


def inbox(session: Session, viewer: Viewer, status: str = "pending", kind: str | None = None) -> dict[str, Any]:
    """승인함 — 종류별 항목 · 건수. status: pending | approved | rejected | ""(전체)."""
    status = status if status in STATUSES else ""
    items: list[dict[str, Any]] = []
    if kind in (None, "", "analysis"):
        items += _analysis_items(session, viewer, status)
    if kind in (None, "", "metric"):
        items += _metric_items(session, viewer, status)
    if kind in (None, "", "concept"):
        items += _concept_items(session, viewer, status, _schema_ko(session))
    if kind in (None, "", "ontology"):
        items += _ontology_items(session, viewer, status)
    counts = pending_counts(session, viewer)
    return {"scope": viewer.scope_json(), "admin": viewer.admin, "items": items, "counts": counts,
            "spaces": [{"key": k, "label": sp.get("label") or k} for k, sp in builder_spaces(session).items()]}


def pending_counts(session: Session, viewer: Viewer) -> dict[str, int]:
    """처리할 건수(본인이 요청한 분석은 빼고) — 종류별 · 합계."""
    a = sum(1 for i in _analysis_items(session, viewer, "pending") if i["canReview"])
    m = len(_metric_items(session, viewer, "pending"))
    c = len(_concept_items(session, viewer, "pending", {}))
    o = sum(1 for i in _ontology_items(session, viewer, "pending") if i["canReview"])
    return {"analysis": a, "metric": m, "concept": c, "ontology": o, "total": a + m + c + o}


def pending_total(session: Session, user: Any) -> int:
    """사이드바 건수(menu_counts) — 책임자 · 관리자가 아니면 0."""
    v = viewer_of(session, user)
    return pending_counts(session, v)["total"] if v is not None else 0


# ═════════════════════════ 결정 — 분석 ═════════════════════════
def _version(session: Session, code: str, version: int) -> tuple[AnalysisAgent, AnalysisAgentVersion]:
    a = session.get(AnalysisAgent, code, with_for_update=True)
    v = session.execute(select(AnalysisAgentVersion).where(AnalysisAgentVersion.agent_code == code, AnalysisAgentVersion.version == version)).scalar() if a else None
    if a is None or v is None:
        raise StewardError(404, "분석 요청 없음")
    return a, v


def _reviewable_analysis(session: Session, viewer: Viewer, code: str, version: int) -> tuple[AnalysisAgent, AnalysisAgentVersion]:
    a, v = _version(session, code, version)
    if not _visible_analysis(session, viewer, v):
        raise StewardError(404, "분석 요청 없음")  # 다른 부서 것은 없는 것처럼
    if v.status != "pending":
        raise StewardError(409, "승인 대기 상태가 아닙니다")
    if v.requested_by == viewer.emp_no:
        raise StewardError(409, "본인이 요청한 분석은 다른 책임자나 관리자가 승인해야 합니다")
    return a, v


def approve_analysis(session: Session, viewer: Viewer, code: str, version: int, *, note: str | None = None, options: dict[str, Any] | None = None,
                     space: str | None = None) -> dict[str, Any]:
    """승인 = 분석 에이전트 생성(lifecycle.approve — 관리자 승인과 같은 경로). 아직 한 번도 승인되지 않은 분석이면 공간을 바꿀 수 있다."""
    from nhdip.analysis_agents.lifecycle import LifecycleError, approve

    a, v = _reviewable_analysis(session, viewer, code, version)
    if space and space != a.space:
        if a.version:
            raise StewardError(422, "이미 동작 중인 분석은 공간을 바꿀 수 없습니다 — 새로 요청하세요")
        if space not in builder_spaces(session):
            raise StewardError(422, f"분석을 둘 수 없는 공간입니다: {space}")
        a.space = space
        v.spec = {**(v.spec or {}), "space": space}
    try:
        return approve(session, a, v, viewer.emp_no, note, options)
    except LifecycleError as exc:
        raise StewardError(422, str(exc)) from exc


def reject_analysis(session: Session, viewer: Viewer, code: str, version: int, note: str) -> None:
    from nhdip.analysis_agents.lifecycle import LifecycleError, reject

    if not (note or "").strip():
        raise StewardError(422, "반려 사유를 적어 주세요")
    a, v = _reviewable_analysis(session, viewer, code, version)
    try:
        reject(session, a, v, viewer.emp_no, note.strip()[:1000])
    except LifecycleError as exc:
        raise StewardError(422, str(exc)) from exc


# ═════════════════════════ 결정 — 지표 ═════════════════════════
def decide_metric(session: Session, m: Metric | None, actor: str, *, approve: bool, note: str | None = None) -> None:
    """제안 지표 승인(켜고 바로 계산) · 반려(꺼 둔 채 표시 — 같은 열을 다시 제안하지 않음). 관리자 화면 · 승인함이 같이 쓴다."""
    from nhdip.workflow.metric_nodes import APPROVED, PROPOSED, REJECTED, WORKFLOW

    if m is None or m.workflow_code != WORKFLOW or not (m.description or "").startswith(PROPOSED) or m.enabled:
        raise StewardError(404, "제안 지표 없음")
    body = (m.description or "").removeprefix(PROPOSED).strip()
    if approve:
        m.enabled = True
        m.description = f"{APPROVED} {body}"[:900]
        emit(session, "config.changed", {"kind": "metric", "code": m.code}, actor)
        emit(session, "manual", {"workflow": WORKFLOW, "reason": f"제안 지표 승인 {m.code}"}, actor)  # 바로 계산
    else:
        m.description = f"{REJECTED} {body}" + (f" — 반려 사유: {note.strip()}" if (note or "").strip() else "")
        m.description = m.description[:900]


def review_metric(session: Session, viewer: Viewer, code: str, *, approve: bool, note: str | None = None) -> Metric:
    m = session.get(Metric, code, with_for_update=True)
    if m is None or not can_review_dataset(session, viewer, metric_dataset(session, m)):
        raise StewardError(404, "제안 지표 없음")
    decide_metric(session, m, viewer.emp_no, approve=approve, note=note)
    return m


# ═════════════════════════ 결정 — 개념 연결 ═════════════════════════
def _concept_entry(entries: list[Any], label: str, key: str) -> dict[str, Any] | None:
    return next((c for c in entries if isinstance(c, dict) and c.get("label") == label and c.get("key") == key), None)


def review_concept(session: Session, viewer: Viewer, dataset: str, label: str, key: str, *, approve: bool, note: str | None = None) -> Dataset:
    """승인 = 자료 정의 mapping.concepts 에 '이 자료는 그 개념에 관한 것'(about · DESCRIBES)으로 더하고 그래프 · 설명 카드를 다시 맞춘다."""
    from nhdip.graph.projection import active_schema

    ds = session.get(Dataset, dataset, with_for_update=True)
    if ds is None or not can_review_dataset(session, viewer, ds):
        raise StewardError(404, "개념 연결 제안 없음")
    m = copy.deepcopy(ds.mapping or {})
    props = list(m.get(PROPOSED_CONCEPTS) or [])
    hit = _concept_entry(props, label, key)
    if hit is None:
        raise StewardError(404, "개념 연결 제안 없음")
    props = [c for c in props if c is not hit]
    now = utcnow().isoformat()
    if approve:
        sc = active_schema(session)
        labels = {c.get("label") for c in (sc.classes if sc is not None else []) or [] if c.get("kind") == "concept"}
        if label not in labels:
            raise StewardError(409, f"온톨로지에 개념 종류 '{label}' 이 없습니다(스키마가 바뀜) — 반려하세요")
        concepts = [c for c in (m.get("concepts") or []) if not (isinstance(c, dict) and c.get("label") == label and c.get("key") == key)]
        concepts.append({"label": label, "key": key, "name": hit.get("name") or key, "about": True, "proposedBy": hit.get("by") or "agent", "score": hit.get("score"),
                         "evidence": (hit.get("evidence") or [])[:5], "reason": hit.get("reason"), "approvedBy": viewer.emp_no, "approvedAt": now, **({"note": note.strip()[:300]} if (note or "").strip() else {})})
        m["concepts"] = concepts
    else:
        if not (note or "").strip():
            raise StewardError(422, "반려 사유를 적어 주세요")
        rej = [c for c in (m.get(REJECTED_CONCEPTS) or []) if not (isinstance(c, dict) and c.get("label") == label and c.get("key") == key)]
        rej.append({**hit, "rejectedBy": viewer.emp_no, "rejectedAt": now, "note": note.strip()[:300]})
        m[REJECTED_CONCEPTS] = rej[-200:]
    m[PROPOSED_CONCEPTS] = props
    ds.mapping = m
    if approve:
        # 그래프 재투영(wf_graph_projection) · 구조 파악 재실행이 깨어난다 — 설명 카드 개념 태그는 호출한 쪽이 커밋 뒤에 맞춘다
        emit(session, "config.changed", {"kind": "dataset", "code": ds.code, "reason": "concept_link"}, viewer.emp_no)
    return ds


# ═════════════════════════ 결정 — 온톨로지 변경 ═════════════════════════
def review_ontology(session: Session, viewer: Viewer, pid: int, *, approve: bool, note: str | None = None) -> tuple[OntologyProposal, dict[str, Any]]:
    """승인 = 관리자 승인과 같은 경로(graph.proposals.decide — 활성 스키마에 적용 → 검증 → 새 판 → ontology.changed).
    책임자는 연산을 골라 빼지 못한다(전부 적용 · 반려) — 일부만 적용하려면 관리자 [온톨로지 › 변경 제안]. 적용 검증 실패는 제안을 failed 로 남긴다."""
    from nhdip.graph.proposals import decide

    p = session.get(OntologyProposal, pid, with_for_update=True)
    if p is None or p.status not in ONTO_STATUS or not can_review_ontology(session, viewer, p):
        raise StewardError(404, "온톨로지 변경 제안 없음")  # 다른 부서 · 전행 제안은 없는 것처럼
    if p.status != "pending":
        raise StewardError(409, "승인 대기 상태가 아닙니다")
    if p.created_by and p.created_by == viewer.emp_no:
        raise StewardError(409, "본인이 만든 제안은 다른 책임자나 관리자가 승인해야 합니다")
    text = (note or "").strip()[:1000]
    if not approve and not text:
        raise StewardError(422, "반려 사유를 적어 주세요")
    return p, decide(session, p, approve=approve, actor=viewer.emp_no, note=text or None)


def linked_concepts(session: Session, ds: Dataset, resolver: Any = None) -> list[dict[str, Any]]:
    """자료에 이어진 업무 개념(승인된 연결 + 업무 구성의 연결) — 설명 카드 · 검색 개념 태그용."""
    from nhdip.data.sources import Resolver

    res = resolver or Resolver(session)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for m in [ds.mapping or {}, *res.mappings_for(ds.code)]:
        for c in m.get("concepts") or []:
            if isinstance(c, dict) and c.get("label") and c.get("key") and (c["label"], c["key"]) not in seen:
                seen.add((c["label"], c["key"]))
                out.append({"label": c["label"], "key": c["key"], "name": c.get("name") or c["key"]})
    return out
