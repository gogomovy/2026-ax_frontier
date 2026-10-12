"""화면 API — 프론트 `src/lib/data.ts` 함수와 1:1 (응답 형식 동일).

화면 산출물은 app.view_artifact 의 현재 세대에서, 데이터셋·문서 목록은 원장(bank/ext)에서 만든다.
각 엔드포인트는 리소스 키 단위로 화면 권한을 검사한다.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.graph.evidence import doc_visible
from nhdip.graph.search import graph_documents, hybrid_search
from nhdip.models import AppUser, Dataset, Setting, source
from nhdip.views.store import find_insight, get_current, get_current_row

from .deps import require_resource

router = APIRouter(prefix="/screens", tags=["screens"])


def _artifact(session: Session, key: str) -> Any:
    v = get_current(session, key)
    if v is None:
        raise HTTPException(404, f"산출물 없음: {key}")
    return v


def _simple(path: str, key: str, resource: str):
    def handler(session: Session = Depends(get_session), _: AppUser = Depends(require_resource(resource))):
        return _artifact(session, key)

    handler.__name__ = f"get_{key}"
    router.add_api_route(path, handler, methods=["GET"], name=key)


for _path, _key, _res in [
    ("/domains", "domains", "domains"),
    ("/hq-dashboard", "hq_dashboard", "hq_dashboard"),
    ("/attentions", "attentions", "attentions"),
    ("/loan-overview", "loan_overview", "loan_overview"),
    ("/comparison-view", "comparison_view", "comparison_view"),
    ("/capital-view", "capital_view", "capital_view"),
    ("/profitability", "profitability", "profitability"),
    ("/goals", "goals", "goals"),
    ("/proposals", "proposals", "proposals"),
    ("/review-queue", "review_queue", "review_queue"),
    ("/cascade", "cascade", "cascade"),
    ("/risk-dashboard", "risk_dashboard", "risk_dashboard"),
    ("/analysis-tabs", "analysis_tabs", "analysis_tabs"),
    ("/inclusive", "inclusive", "inclusive"),
    ("/default-rate-trend", "default_rate_trend", "default_rate_trend"),
    ("/branch-targets", "branch_targets", "branch_targets"),
    ("/terms", "terms", "terms"),
]:
    _simple(_path, _key, _res)


@router.get("/report-requests")
def report_requests(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("report_requests"))):
    """보고 · 확인 요청 — 산출물 + 영업점 · 부서가 직접 등록한 요청(최근 순) (B.32)."""
    from nhdip.views.user_state import NS_REPORT_REQUEST, get_ns

    base = _artifact(session, "report_requests") or []
    users = sorted(get_ns(session, NS_REPORT_REQUEST).values(), key=lambda r: r.get("createdAt", ""), reverse=True)
    return [{k: v for k, v in r.items() if k != "createdBy"} for r in users] + list(base)


@router.get("/action-plans")
def action_plans(session: Session = Depends(get_session), user: AppUser = Depends(require_resource("action_plans"))):
    """수행방안 — 수정 권한(plan_actions)이 없는 사용자(영업점 등)에게는 영업점 참고가 켜진 진행사업만 (B.32)."""
    from nhdip.views.user_state import merged_plans

    from .deps import user_resources

    plans = _artifact(session, "action_plans")
    allowed = user_resources(session, user)
    if allowed is None or "plan_actions" in allowed:
        return plans
    shared = {p["id"] for p in merged_plans(session) if p.get("branchShared") and p.get("status") == "in_progress"}
    return [p for p in plans if p.get("id") in shared]


@router.get("/producer")
def producer(key: str, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("meta"))):
    """산출물을 만드는 워크플로우 코드 — 화면의 '분석 다시 실행' · 변화 피드 필터 대상 (프론트에 워크플로우 코드를 두지 않는다)."""
    return {"key": key, "workflow": _producer(session, key)}


@router.get("/meta")
def meta(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("meta"))):
    """화면 상단 기준일 · 최근 계산 시각 (AppShell)."""
    from nhdip.models import ViewArtifact, WorkflowRun

    as_of = session.get(Setting, "ui.as_of")
    last = session.execute(select(func.max(ViewArtifact.created_at)).where(ViewArtifact.is_current)).scalar()
    last_run = session.execute(select(WorkflowRun).where(WorkflowRun.status.in_(["succeeded", "degraded"])).order_by(WorkflowRun.finished_at.desc()).limit(1)).scalar()
    return {
        "asOf": as_of.value if as_of else None,
        "generatedAt": last.isoformat() if last else None,
        "lastRun": {"workflow": last_run.workflow_code, "status": last_run.status, "finishedAt": last_run.finished_at.isoformat() if last_run.finished_at else None} if last_run else None,
    }


@router.get("/domains/{code}")
def domain(code: str, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("domains"))):
    for d in _artifact(session, "domains"):
        if d.get("domainCode") == code:
            return d
    raise HTTPException(404, "사업부문 없음")


@router.get("/goals/{goal_id}")
def goal(goal_id: str, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("goals"))):
    for g in _artifact(session, "goals"):
        if g.get("id") == goal_id:
            return g
    raise HTTPException(404, "목표 없음")


def _producer(session: Session, key: str) -> str | None:
    """산출물을 만드는 워크플로우 — 화면의 '분석 다시 실행' 대상 (프론트에 매핑을 두지 않는다)."""
    from nhdip.models import Workflow

    for w in session.execute(select(Workflow).where(Workflow.enabled).order_by(Workflow.sort)).scalars():
        if key in (w.outputs or []):
            return w.code
    return None


@router.get("/reports/{tab_key}")
def report(tab_key: str, session: Session = Depends(get_session), _: AppUser = Depends(require_resource("reports"))):
    row = get_current_row(session, f"report.{tab_key}")
    if not row:
        raise HTTPException(404, "보고서 없음")
    return {**row.payload, "workflow": _producer(session, f"report.{tab_key}")}


# ── 영업점 (B.29) — 산출물의 영업점(office.code)과 사용자 소속을 대조한다 (Q44) ──
def _viewer_office(session: Session, user: AppUser) -> dict[str, Any] | None:
    from nhdip.orgs import branch_of, office_code_of

    br = branch_of(session, user.org_code)
    return {"code": office_code_of(session, br.code), "name": br.name, "orgCode": br.code} if br else None


OFFICE_Q = Query(None, pattern=r"^[A-Za-z0-9_-]{1,20}$", description="지점(사무소) 코드 — 비우면 사용자 소속 영업점, 없으면 기본 지점 (B.47)")


def branch_artifact(session: Session, user: AppUser, key: str, office: str | None = None) -> Any:
    """영업점 산출물 — 볼 지점(주소 인자 · 소속 · 기본)의 범위 키('<키>@<지점>', 기본 지점은 기존 키)를 읽고 열람 범위를 검사한다 (B.47 · Q44)."""
    from nhdip.orgs import can_view_office
    from nhdip.scopes import office_scope, resolve_office, scoped_key

    primary, _ = office_scope(session)
    target = resolve_office(session, user, office)
    if office and not can_view_office(session, user, office):
        # 열람 범위 밖 지점을 주소로 요청 — 감사에 남기고 없는 것처럼 응답 (BRM-04)
        from nhdip.events import audit

        audit(session, user.emp_no, "branch.office_denied", "office", str(office)[:20], {"artifact": key})
        session.commit()
        return None
    v = get_current(session, scoped_key(key, target, primary))
    if not isinstance(v, dict):
        return None
    code = (v.get("office") or {}).get("code")
    if not code or (target and str(code) != str(target)):
        return None
    return v if can_view_office(session, user, code) else None



@router.get("/branch/offices")
def branch_offices(session: Session = Depends(get_session), user: AppUser = Depends(require_resource("branch_dashboard"))):
    """볼 수 있는 계산 대상 지점 목록 (B.47 · BRM-05) — 지역본부 · 관리자 화면의 지점 선택 상자. 영업점 직원은 자기 지점 하나."""
    from nhdip.orgs import can_view_office, org_of_office
    from nhdip.scopes import office_scope, resolve_office, scoped_key

    primary, offices = office_scope(session)
    out = []
    for code in offices:
        if not can_view_office(session, user, code):
            continue
        v = get_current(session, scoped_key("branch_dashboard", code, primary))
        org = org_of_office(session, code)
        name = ((v or {}).get("office") or {}).get("name") if isinstance(v, dict) else None
        out.append({"code": code, "name": name or (org.name if org else code), "available": isinstance(v, dict), "primary": code == primary})
    return {"offices": out, "default": resolve_office(session, user, None)}


@router.get("/branch/dashboard")
def branch_dashboard(office: str | None = OFFICE_Q, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("branch_dashboard"))):
    """영업점 1화면 — 열람 범위 밖이거나 분석이 없는 영업점이면 available=false 와 사용자 영업점만 돌려준다."""
    v = branch_artifact(session, user, "branch_dashboard", office)
    if v is None:
        return {"available": False, "viewer": _viewer_office(session, user)}
    return {**v, "available": True, "viewer": _viewer_office(session, user), "workflow": _producer(session, "branch_dashboard")}


@router.get("/branch/tabs")
def branch_tabs(office: str | None = OFFICE_Q, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("branch_tabs"))):
    v = branch_artifact(session, user, "branch_tabs", office)
    return v if v is not None else {"current": [], "previous": []}


@router.get("/branch/reports/{tab_key}")
def branch_report(tab_key: str, office: str | None = OFFICE_Q, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("branch_reports"))):
    v = branch_artifact(session, user, f"report.branch-{tab_key}", office)
    if v is None:
        raise HTTPException(404, "보고서 없음")
    return {**v, "workflow": _producer(session, f"report.branch-{tab_key}")}


@router.get("/changes")
def changes(workflow: str | None = None, limit: int = 20, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("changes"))):
    """변화 감지 에이전트의 최근 유의 변화 (B.30) — 사용자가 볼 수 있는 워크플로우 · 영업점 범위만."""
    from nhdip.orgs import can_view_office

    from .deps import user_resources

    feed = get_current(session, "change_feed") or {}
    allowed = user_resources(session, user)
    wf_res_s = session.get(Setting, "assist.workflow_resources")
    wf_res = wf_res_s.value if wf_res_s and isinstance(wf_res_s.value, dict) else {}
    out = []
    for it in feed.get("items") or []:
        if workflow and it.get("workflow") != workflow:
            continue
        if allowed is not None and wf_res.get(it.get("workflow")) not in allowed:
            continue
        office = (it.get("scope") or {}).get("office")
        if office and not can_view_office(session, user, office):
            continue
        out.append(it)
        if len(out) >= min(max(limit, 1), 100):
            break
    return {"items": out, "updatedAt": feed.get("updatedAt")}


@router.get("/insights/{insight_id}")
def insight(insight_id: str, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("insights"))):
    from .deps import user_resources

    # 다른 부서 화면의 인사이트는 그 화면 리소스가 있을 때만 (B.32 — insights 리소스만으로 부서 간 열람 불가)
    allowed = user_resources(session, user)
    keys = [k for k in ("insights", "attentions", "risk_dashboard", "hq_dashboard") if allowed is None or k in allowed]
    arts = {k: get_current(session, k) for k in keys}
    ins = find_insight({k: v for k, v in arts.items() if v is not None}, insight_id)
    if not ins:
        raise HTTPException(404, "인사이트 없음")
    return ins


# ── 원장 기반 목록 ────────────────────────────────────────────
STATUS_MAP = {"extracted": "ready", "partial": "ready", "ingested": "parsing", "failed": "pending"}


def _documents(session: Session, user: AppUser | None = None) -> list[dict[str, Any]]:
    labels_s = session.get(Setting, "doc_class.labels")
    labels = labels_s.value if labels_s else {}
    out = []
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in session.execute(select(t.document).where(t.document.is_current).order_by(t.document.created_at)).scalars():
            m = dict(d.meta or {})
            if not doc_visible(session, user, d.doc_code, m)[0]:
                continue  # 부서한정 문서 — 소유 부서 밖 사용자에게 목록 미노출 (8.4.2)
            n_chunks = session.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == d.id)).scalar() or 0
            ex = d.extraction or {}
            out.append(
                {
                    "docId": d.doc_code,
                    "title": d.title,
                    "dbClass": d.doc_class,
                    "dbClassLabel": labels.get(d.doc_class, m.get("dbClassLabel", d.doc_class)),
                    "docType": m.get("docType", "업로드 문서"),
                    "issuer": d.issuer or m.get("issuer", "-"),
                    "effectiveDate": d.published_at.isoformat() if d.published_at else m.get("effectiveDate", ""),
                    "registeredAt": m.get("registeredAt") if d.uploaded_by == "seed" else d.created_at.date().isoformat(),
                    "domainLabels": m.get("domainLabels", []),
                    "tags": m.get("tags", []),
                    "accessClass": m.get("accessClass", "public" if origin == "ext" else "internal"),
                    "pageCount": m.get("pageCount", max(1, n_chunks)),
                    "isOfficial": m.get("isOfficial", origin == "ext"),
                    "ingestStatus": STATUS_MAP.get(d.status, "pending"),
                    "usedByCount": m.get("usedByCount", len(ex.get("relations") or [])),
                    "fileName": d.file_name or m.get("fileName", ""),
                    # 확장 필드 (프론트 타입에 없는 값 — 무시돼도 무방)
                    "origin": origin,
                    "version": d.version,
                    "chunks": n_chunks,
                    "extractedBy": ex.get("by"),
                }
            )
    return out


@router.get("/documents")
def documents(db_class: str | None = Query(None, alias="dbClass"), session: Session = Depends(get_session), user: AppUser = Depends(require_resource("documents"))):
    docs = _documents(session, user)
    return [d for d in docs if not db_class or d["dbClass"] == db_class]


@router.get("/datasets")
def datasets(session: Session = Depends(get_session), _: AppUser = Depends(require_resource("datasets"))):
    """DatasetMeta[] — 확정된 현재 버전(기준일 구획별)."""
    out = []
    for ds in session.execute(select(Dataset).where(Dataset.active).order_by(Dataset.origin, Dataset.code)).scalars():
        t = source(ds.origin)
        for v in session.execute(select(t.version).where(t.version.dataset_code == ds.code, t.version.is_current).order_by(t.version.as_of.desc().nullslast())).scalars():
            q = v.quality or {}
            bad = [c for c in q.get("checks", []) if not c.get("passed")]
            out.append(
                {
                    "fileName": v.file_name or f"{ds.code} v{v.version}",
                    "reportCode": (ds.mapping or {}).get("report_code", ds.code),
                    "asOfYm": v.as_of.strftime("%Y%m") if v.as_of else "-",
                    "rows": v.row_count,
                    "unit": (ds.mapping or {}).get("unit", "-"),
                    "quality": q.get("status", "passed"),
                    "qualityNote": "; ".join(f"{c['rule']}: {c['detail']}" for c in bad[:2]) or "품질 검증 통과",
                    "registeredAt": (v.committed_at or v.created_at).date().isoformat(),
                    "usedBy": (ds.mapping or {}).get("used_by", []),
                    "origin": ds.origin,
                    "dataset": ds.code,
                    "datasetName": ds.name,
                    "version": v.version,
                    "dataOrigin": v.data_origin,
                }
            )
    return out


@router.get("/search")
def search(q: str, concepts: str | None = None, k: int = 5, domain: str | None = None, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("search"))):
    """근거 검색 — 그래프 필터 → 키워드(+벡터) RRF → 근거 선별(게이팅 · 우선순위 · 범주 균형, 거부 사유 포함)."""
    from nhdip.graph.evidence import rank_evidence
    from nhdip.graph.search import query_terms

    cs = [c.strip() for c in (concepts or "").split(",") if c.strip()]
    flt = graph_documents(cs) if cs else None
    k = min(max(k, 1), 20)
    as_of = session.get(Setting, "ui.as_of")
    ranked = rank_evidence(session, hybrid_search(session, q, doc_filter=flt, k=k * 3), k=k, user=user, as_of=as_of.value if as_of else None, domain=domain, doc_filter=flt, query_terms=len(query_terms(q)))
    return {"graphFilter": flt, "hits": ranked["hits"], "rejected": ranked["rejected"], "categories": ranked["categories"], "missingCategories": ranked["missingCategories"]}
