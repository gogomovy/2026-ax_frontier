"""수행방안 '영업점 참고' — 사업부서가 진행사업의 영업점 참고를 켜면, 그 수행방안과 연결된 자료를 '영업점 공통'(영업본부 · 영업점)이 함께 쓴다.
별도 기능이 아니라 수행방안의 영업점 참고 하나로 간다(끄면 함께 빠진다).

연결은 복사가 아니라 권한이다(branch_grant) — 질의 때마다 지금 원장에서 '영업점 참고 수행방안 → 연결 자료' 를 다시 짚는다.
사업부서가 다시 계산하면 같은 산출물 키 · 문서 코드 · 데이터셋 코드의 새 세대가 원장(PostgreSQL · Elasticsearch · Neo4j)에 들어가고,
영업점 공통은 그 키로 이어져 있으므로 따로 내려 줄 것이 없다.

  연결 자료      — 연결 분석 보고서(연결 분석 탭 · 근거 인사이트의 탭) · 그 보고서 · 수행방안 · 근거 인사이트가 인용한 근거 문서 ·
                  그 보고서 수치를 계산하는 데이터셋(지표 계보 · 화면 바인딩 · 분석 에이전트 명세)
  영업점 화면     — 수행방안 상세의 '연결 분석' 요약 + 공유 보고서 화면(/branch/shared/{수행방안}) — 부서 보고서 화면 권한 없이
  질문하기       — 연결 보고서 청크 · 근거 문서 청크를 '영업점 공통' 으로 함께 검색, 연결 데이터셋은 집계 도구로(행 원문 없이)
                  + 영업점 참고 수행방안 요약 산출물(branch_shared_plans)을 영업점 공통 컬렉션에 색인
  그래프         — 수행방안 노드(Plan)가 연결 보고서 · 문서 · 데이터셋과 이어진다(graph.projection) — 탐색용, 권한은 위 SQL · ES 규칙
  영업점 에이전트  — 영업점 산출물을 만드는 흐름의 서술(narrate)이 근거로 읽는다(수치 이름만 — 숫자는 영업점 자체 확정 수치 마커로)
  다시 계산       — 영업점 참고를 바꾸면 이벤트(plan.branch_shared · plan.branch_unshared)로 영업점 흐름 · 그래프 투영이 다시 돌고,
                  연결 분석 보고서가 다시 게시되면 질문하기 요약 색인도 따라 갱신(n_publish)

분석은 늘 지금 보고서 기준이다 — 계산 전(값 없는 틀) 보고서는 요약하지 않는다(readiness.gate).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Workflow, source

from .store import find_insight, get_current, get_current_row, publish
from .user_state import merged_plans

log = logging.getLogger(__name__)

ARTIFACT_KEY = "branch_shared_plans"
SHARE_EVENTS = ("plan.branch_shared", "plan.branch_unshared")
MAX_SUMMARY = 6
MAX_FIGS = 12
MAX_SECTIONS = 8
MAX_LINES = 10
AGENT_ITEMS = 6


# ── 영업점 흐름 ───────────────────────────────────────────────
def is_branch_outputs(outputs: list[Any] | None) -> bool:
    """영업점 산출물(업적평가 화면 · 영업점 보고서)을 만드는 흐름 — 영업점 참고 수행방안을 서술 근거로 읽고, 참고가 바뀌면 다시 돈다."""
    return any(isinstance(o, str) and (o == "branch_dashboard" or o.startswith("report.branch-")) for o in outputs or [])


def branch_workflows(session: Session) -> list[str]:
    return [w.code for w in session.execute(select(Workflow).where(Workflow.enabled).order_by(Workflow.sort, Workflow.code)).scalars() if is_branch_outputs(w.outputs)]


def shared_plans(session: Session) -> list[dict[str, Any]]:
    """영업점 참고가 켜진 진행사업 (screens.action_plans · user_state.shared_plan_state 와 같은 기준)."""
    return [p for p in merged_plans(session) if p.get("branchShared") and p.get("status") == "in_progress"]


# ── 연결 분석 ─────────────────────────────────────────────────
def space_of_tab(session: Session, tab_key: str) -> dict[str, Any] | None:
    """분석 탭의 분석 공간 — 분석 에이전트 탭(an-*)은 에이전트의 공간, 기존 탭은 탭 목록 산출물에 그 탭이 있는 공간(설정 analysis.spaces)."""
    from nhdip.analysis_registry import agent_for_tab, space, spaces

    a = agent_for_tab(session, tab_key)
    if a is not None:
        return space(session, a.space)
    for sp in spaces(session).values():
        if not sp.get("tabs"):
            continue
        tabs = get_current(session, sp["tabs"]) or {}
        if isinstance(tabs, dict) and any(isinstance(t, dict) and t.get("tabKey") == tab_key for t in [*(tabs.get("current") or []), *(tabs.get("previous") or [])]):
            return sp
    return None


def tab_of(session: Session, plan: dict[str, Any]) -> str | None:
    """수행방안의 분석 탭 — 연결 분석(linkedTabKey), 없으면 근거 인사이트(sourceInsightId)가 있는 탭."""
    if plan.get("linkedTabKey"):
        return str(plan["linkedTabKey"])
    sid = plan.get("sourceInsightId")
    if not sid:
        return None
    from .readiness import INSIGHT_KEYS

    arts = {k: v for k in INSIGHT_KEYS if (v := get_current(session, k)) is not None}
    ins = find_insight(arts, str(sid))
    return str(ins["tabKey"]) if isinstance(ins, dict) and ins.get("tabKey") else None


def _usable(f: Any) -> bool:
    return isinstance(f, dict) and f.get("value") is not None and not f.get("stale") and "label" in f


def summarize(report: dict[str, Any], tab_key: str, sp: dict[str, Any]) -> dict[str, Any]:
    """보고서 요약 — 의견(값을 넣은 문장 · 수치 이름만 쓴 문장 brief) · 주요 수치 · 절 요약 · 한계. 색인과 같은 표기 · 개인정보 형식 값은 가림."""
    from nhdip.analysis_registry import report_severity
    from nhdip.knowledge.render import collect_figures, fig_line, resolve_labels, resolve_text, section_lines
    from nhdip.privacy import mask_text

    figs = collect_figures(report)
    summary: list[dict[str, Any]] = []
    key_figs: list[str] = []
    seen: set[str] = set()

    def add_fig(fid: str, f: Any) -> None:
        if _usable(f) and fid not in seen and len(key_figs) < MAX_FIGS:
            seen.add(fid)
            key_figs.append(fig_line(f))

    for o in (report.get("opinions") or [])[:MAX_SUMMARY]:
        if not isinstance(o, dict):
            continue
        st = o.get("statement") if isinstance(o.get("statement"), str) else ""
        local = {**figs, **{k: v for k, v in (o.get("figures") or {}).items() if isinstance(v, dict)}}
        summary.append({"title": mask_text(str(o.get("title") or "")), "severity": o.get("severity") or "info",
                        "text": mask_text(resolve_text(st, local).strip()), "brief": mask_text(resolve_labels(st, local).strip())})
        for fid, f in (o.get("figures") or {}).items():
            add_fig(fid, f)
    for fid, f in (report.get("figures") or {}).items():
        add_fig(fid, f)
    sections = []
    for sec in report.get("sections") or []:
        if not isinstance(sec, dict) or sec.get("id") == "sec-team" or len(sections) >= MAX_SECTIONS:
            continue
        lines = [ln for ln in section_lines(report, sec.get("blocks") or []) if ln.strip()][:MAX_LINES]
        if lines:
            sections.append({"heading": mask_text(str(sec.get("heading") or "")), "lines": lines})
    return {
        "tabKey": tab_key, "space": sp["key"], "analysisFrom": sp.get("label") or sp["key"],
        "title": mask_text(str(report.get("title") or tab_key)), "subtitle": mask_text(str(report.get("subtitle") or "")),
        "asOf": report.get("asOf"), "asOfLabel": str(report.get("asOf") or "")[:10] or None, "severity": report_severity(report),
        "summary": summary, "keyFigures": key_figs, "sections": sections,
        "limitations": [mask_text(str(x)) for x in (report.get("limitations") or []) if isinstance(x, str) and x.strip()][:6],
    }


def linked_analysis(session: Session, plan: dict[str, Any]) -> dict[str, Any] | None:
    """수행방안의 연결 분석 요약 — 지금 보고서 기준. 탭이 없거나 · 공간을 모르거나 · 아직 계산 전이면 None."""
    from nhdip.analysis_registry import report_key

    from .readiness import gate

    tab = tab_of(session, plan)
    sp = space_of_tab(session, tab) if tab else None
    if not tab or sp is None:
        return None
    key = report_key(sp, tab)
    row = get_current_row(session, key)
    report = gate(key, row.payload) if row is not None else None
    return summarize(report, tab, sp) if isinstance(report, dict) else None


def public(a: dict[str, Any] | None) -> dict[str, Any] | None:
    """화면 · 색인용 — 에이전트용 요약(brief)은 뺀다."""
    if a is None:
        return None
    return {**a, "summary": [{k: v for k, v in s.items() if k != "brief"} for s in a.get("summary") or [] if isinstance(s, dict)]}


SHARED_PATH = "/branch/shared"  # 영업점 공통 공유 보고서 화면 (웹 app/branch/shared/[planId])


def report_href(session: Session, a: dict[str, Any], allowed: set[str] | None, shared_plan: str | None = None) -> str | None:
    """연결 분석 보고서 화면 주소 — 그 공간 보고서 열람 리소스가 있으면 부서 보고서 화면,
    없고 영업점 공통이면(shared_plan = 수행방안 id) 공유 보고서 화면, 둘 다 아니면 None(요약만 본다)."""
    from nhdip.analysis_registry import space

    sp = space(session, a.get("space") or "")
    if sp is not None and sp.get("path") and (allowed is None or sp.get("resource") in allowed):
        return f"{sp['path']}/{a['tabKey']}"
    return f"{SHARED_PATH}/{shared_plan}" if shared_plan else None


# ── 영업점 공통 — 영업본부 · 영업점이 영업점 참고 수행방안의 연결 자료를 함께 쓴다 ─────────
BRANCH_COMMON_RESOURCES = ("branch_targets", "branch_dashboard", "region_kpi")  # 영업점 · 영업본부 화면 리소스(하나라도 있으면 영업점 공통)
BRANCH_COMMON_TYPES = ("REGION", "BRANCH")  # 소속 경로에 이 조직 유형이 있으면 영업점 공통(지역본부 · 영업점)
GRANT_LABEL = "영업점 공통"


def in_branch_common(session: Session, user: Any, resources: set[str] | None) -> bool:
    """영업점 공통(영업본부 · 영업점) 사용자 — 관리자, 영업점 · 영업본부 화면 리소스가 있거나 소속 경로에 지역본부 · 영업점이 있는 사용자."""
    if getattr(user, "role", None) == "admin" or resources is None:
        return True
    if set(resources) & set(BRANCH_COMMON_RESOURCES):
        return True
    from nhdip.orgs import org_chain

    return any(o.unit_type in BRANCH_COMMON_TYPES for o in org_chain(session, user.org_code))


@dataclass
class BranchGrant:
    """영업점 참고 수행방안의 연결 자료 — 값마다 그 자료를 연 수행방안 id. 요청마다 지금 원장에서 만든다(복사본 · 고정본 없음)."""

    plans: dict[str, dict[str, Any]] = field(default_factory=dict)  # 수행방안 id → {id, title, ownerOrg, tabKey, reportKey, space}
    sources: dict[str, str] = field(default_factory=dict)  # 산출물 키(질문하기 청크 source_key) → 수행방안 id ('' = 영업점 참고 요약)
    docs: dict[str, str] = field(default_factory=dict)  # 문서 코드 → 수행방안 id
    datasets: dict[str, str] = field(default_factory=dict)  # 데이터셋 코드 → 수행방안 id

    def __bool__(self) -> bool:
        return bool(self.plans)

    def plan_of_source(self, key: str) -> str | None:
        pid = self.sources.get(key.split("@", 1)[0])
        return pid or None


def doc_codes(session: Session, objs: list[Any]) -> set[str]:
    """인용 근거의 문서 코드 — 근거 항목(doc · basisDoc 의 docCode), 문서 코드가 없는 옛 근거는 구간 참조(chunkRef)로 찾는다."""
    codes: set[str] = set()
    chunks: set[tuple[str, int]] = set()
    stack: list[Any] = list(objs)
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            code = o.get("docCode")
            if isinstance(code, str) and code.strip():
                codes.add(code.strip())
            ref = o.get("chunkRef")
            if isinstance(ref, dict) and ref.get("origin") in ("bank", "ext") and isinstance(ref.get("chunkId"), int) and not (isinstance(o.get("doc"), dict) and o["doc"].get("docCode")):
                chunks.add((str(ref["origin"]), int(ref["chunkId"])))
            stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
        elif isinstance(o, list):
            stack.extend(v for v in o if isinstance(v, (dict, list)))
    for origin in sorted({o for o, _ in chunks}):
        t = source(origin)
        ids = sorted(i for o, i in chunks if o == origin)
        codes |= set(session.execute(select(t.document.doc_code).join(t.chunk, t.chunk.document_id == t.document.id).where(t.chunk.id.in_(ids))).scalars())
    return codes


class _Lineage:
    """보고서 → 데이터셋 — 보고서 수치(figure id)를 내는 지표(참조 지표까지) · 그 산출물의 화면 바인딩 · 분석 에이전트 명세가 읽는 자료.
    요청 하나 동안 지표 · 바인딩 · 자료 정의를 한 번만 읽는다(data.scrub.lineage_keys 의 반대 방향)."""

    def __init__(self, session: Session) -> None:
        from nhdip.data.sources import Resolver
        from nhdip.models import Metric, ViewBinding

        self.session = session
        self.metrics = {m.code: m for m in session.execute(select(Metric).where(Metric.enabled)).scalars()}
        self.bindings = list(session.execute(select(ViewBinding).where(ViewBinding.enabled)).scalars())
        self.resolver = Resolver(session)

    def datasets(self, key: str, payload: dict[str, Any], tab: str | None) -> set[str]:
        from nhdip.analysis_registry import agent_for_tab
        from nhdip.graph.projection import _datasets_in_args
        from nhdip.knowledge.render import collect_figures

        figs = set(collect_figures(payload))
        chosen = {c for c, m in self.metrics.items() if figs & set(m.figure_ids or [c])}
        stack = list(chosen)
        while stack:
            m = self.metrics.get(stack.pop())
            for ref in (m.args or {}).values() if m is not None else []:
                dep = ref.get("metric") if isinstance(ref, dict) else None
                if isinstance(dep, str) and dep not in chosen:
                    chosen.add(dep)
                    stack.append(dep)
        names: set[str] = set()
        for c in chosen:
            if c in self.metrics:
                names |= _datasets_in_args(self.metrics[c].args)
        for b in self.bindings:
            if b.artifact_key == key:
                names |= _datasets_in_args(b.params)
        a = agent_for_tab(self.session, tab) if tab else None
        if a is not None:
            names |= _datasets_in_args(a.spec)
        return {d.code for d in (self.resolver.resolve(n) for n in sorted(names)) if d is not None}


def branch_grant(session: Session) -> BranchGrant:
    """영업점 참고 수행방안이 연결한 자료 — 연결 보고서(+ 영업점 참고 요약 산출물) · 근거 문서 · 계산 데이터셋.
    보고서는 그 탭 하나만 연다(부서 인사이트 · 대시보드 산출물 전체는 열지 않는다)."""
    from nhdip.analysis_registry import report_key

    from .readiness import INSIGHT_KEYS

    g = BranchGrant()
    plans = shared_plans(session)
    if not plans:
        return g
    g.sources[ARTIFACT_KEY] = ""
    lineage: _Lineage | None = None
    arts: dict[str, Any] | None = None
    for p in plans:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        tab = tab_of(session, p)
        sp = space_of_tab(session, tab) if tab else None
        key = report_key(sp, tab) if tab and sp is not None else None
        g.plans[pid] = {"id": pid, "title": p.get("title"), "ownerOrg": p.get("ownerOrg"), "tabKey": tab, "reportKey": key, "space": sp["key"] if sp else None}
        refs: list[Any] = [p]
        datasets: set[str] = set()
        if key:
            g.sources.setdefault(key, pid)
            row = get_current_row(session, key)
            if row is not None and isinstance(row.payload, dict):
                refs.append(row.payload)
                lineage = lineage or _Lineage(session)
                datasets = lineage.datasets(key, row.payload, tab)
        if p.get("sourceInsightId"):
            if arts is None:
                arts = {k: v for k in INSIGHT_KEYS if (v := get_current(session, k)) is not None}
            ins = find_insight(arts, str(p["sourceInsightId"]))
            if isinstance(ins, dict):
                refs.append(ins)
        docs = doc_codes(session, refs)
        g.plans[pid].update(docs=sorted(docs), datasets=sorted(datasets))
        for code in sorted(docs):
            g.docs.setdefault(code, pid)
        for code in sorted(datasets):
            g.datasets.setdefault(code, pid)
    return g


def shared_report(session: Session, plan_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """영업점 공통 공유 보고서 — 영업점 참고 수행방안의 연결 분석 보고서(지금 세대, 계산 전 틀이면 None). (수행방안, 보고서)."""
    from nhdip.analysis_registry import report_key

    from .readiness import gate, session_lookup

    plan = next((p for p in shared_plans(session) if p.get("id") == plan_id), None)
    if plan is None:
        return None
    tab = tab_of(session, plan)
    sp = space_of_tab(session, tab) if tab else None
    if not tab or sp is None:
        return None
    key = report_key(sp, tab)
    row = get_current_row(session, key)
    report = gate(key, row.payload, session_lookup(session)) if row is not None else None
    if not isinstance(report, dict):
        return None
    return plan, {**report, "reportKey": key, "tabKey": tab, "analysisFrom": sp.get("label") or sp["key"]}


# ── 질문하기 색인용 산출물 ───────────────────────────────────────
PLAN_KEYS = ("id", "title", "body", "ownerOrg", "reviewCycle", "relatedGoalTitle", "status")
MAX_LINKED = 12


def branch_payload(session: Session) -> list[dict[str, Any]]:
    """영업점 참고 수행방안 + 연결 분석 요약 + 연결 자료 이름(근거 문서 · 데이터셋) — 영업점 공통 컬렉션(analysis.branch_common)에 색인.
    단위 페르소나를 두지 않는다 — 산출물 키 규칙으로 영업점 공통 컬렉션에 가고, 영업본부 · 영업점 화면 권한으로 열린다."""
    from nhdip.models import Dataset

    grant = branch_grant(session)
    titles: dict[str, str] = {}
    for origin in ("bank", "ext"):
        t = source(origin)
        if grant.docs:
            for code, title in session.execute(select(t.document.doc_code, t.document.title).where(t.document.is_current, t.document.doc_code.in_(sorted(grant.docs)))).all():
                titles.setdefault(code, title)
    ds_names = {d.code: d.name for d in session.execute(select(Dataset).where(Dataset.code.in_(sorted(grant.datasets)))).scalars()} if grant.datasets else {}
    out = []
    for p in shared_plans(session):
        item = {k: p.get(k) for k in PLAN_KEYS if p.get(k) not in (None, "")}
        a = public(linked_analysis(session, p))
        if a:
            item["analysis"] = a
        info = grant.plans.get(str(p.get("id") or "")) or {}
        docs = [titles[c] for c in info.get("docs") or [] if c in titles][:MAX_LINKED]
        data = [f"{ds_names.get(c) or c}({c})" for c in info.get("datasets") or []][:MAX_LINKED]
        if docs:
            item["linkedDocs"] = docs
        if data:
            item["linkedData"] = data
        out.append(item)
    return out


def republish(session: Session, actor: str) -> bool:
    """영업점 참고 산출물을 다시 게시하고 같은 트랜잭션에서 색인한다(바뀐 것이 없으면 그대로). 호출자가 commit."""
    from nhdip.knowledge.indexer import index_artifacts

    payload = branch_payload(session)
    if json.dumps(get_current(session, ARTIFACT_KEY), sort_keys=True, default=str) == json.dumps(payload, sort_keys=True, default=str):
        return False
    publish(session, ARTIFACT_KEY, payload, produced_by=f"plan_share:{actor}")
    session.flush()
    index_artifacts(session, [ARTIFACT_KEY])
    return True


def linked_keys(session: Session) -> set[str]:
    """영업점 참고 수행방안이 기대는 산출물 — 연결 보고서 · 인사이트 산출물. 이것이 다시 게시되면 영업점 참고 산출물도 갱신."""
    from nhdip.analysis_registry import report_key

    from .readiness import INSIGHT_KEYS

    keys: set[str] = set()
    for p in shared_plans(session):
        tab = tab_of(session, p)
        sp = space_of_tab(session, tab) if tab else None
        if tab and sp is not None:
            keys.add(report_key(sp, tab))
        if p.get("sourceInsightId"):
            keys |= set(INSIGHT_KEYS)
    return keys


def refresh_if_linked(session: Session, published: list[str], actor: str) -> bool:
    """흐름이 게시한 산출물 가운데 영업점 참고 수행방안의 연결 분석이 있으면 영업점 참고 산출물을 다시 만든다(실패해도 게시는 유지)."""
    if not published or ARTIFACT_KEY in published:
        return False
    try:
        if not set(published) & linked_keys(session):
            return False
        with session.begin_nested():
            return republish(session, actor)
    except Exception as exc:  # noqa: BLE001 — 색인 실패가 흐름 게시를 막지 않는다(다음 변경 · 대조가 다시 맞춘다)
        log.warning("영업점 참고 산출물 갱신 실패: %s", exc, exc_info=True)
        return False


# ── 영업점 에이전트 입력 ─────────────────────────────────────────
def agent_lines(session: Session, limit: int = AGENT_ITEMS) -> list[str]:
    """영업점 서술 에이전트의 근거 줄 — 영업점 참고 진행사업과 그 연결 분석(수치 이름만, 값 없이).
    숫자는 넣지 않는다 — 서술 검증이 리터럴 숫자를 막고, 확정 수치는 영업점 자체 [[fig]] 마커로만 쓴다."""
    out = []
    for p in shared_plans(session)[:limit]:
        body = " ".join(str(p.get("body") or "").split())[:240]
        line = f"- [사업부서 진행사업 · {p.get('ownerOrg') or '-'}] {p.get('title')}: {body or '(본문 없음)'}"
        a = linked_analysis(session, p)
        if a:
            briefs = " ".join(x.get("brief") or "" for x in (a.get("summary") or [])[:3] if isinstance(x, dict)).strip()
            line += f" / 연결 분석 '{a['title']}': {briefs[:360] or '(의견 없음)'}"
        out.append(line)
    return out
