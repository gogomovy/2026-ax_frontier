"""컬렉션 정의 · 팀별 접근 범위 · 산출물 → 컬렉션 배정 (요구사항 §21.1 KB-04/05 · §21.2 ACL · 설계 §21.3/§21.4).

핵심 원칙 — 접근할 수 없는 청크는 **후보 조회 단계에서** 뺀다(SQL 사전 필터). 가져온 뒤 걸러내면 상위 N 건을 권한 없는
청크가 차지해 결과가 비거나, 건수 · 점수로 존재가 새어 나간다(ACL-01 · ACL-04).

접근 규칙(관리자는 전체)
  ⓐ 담당(owner_orgs) · 공유(shared_orgs) 팀의 조직 경로에 속한다   → 컬렉션 전체
  ⓑ 공개 범위 audience == 'all'                                     → 컬렉션 전체
  ⓒ 컬렉션 required_resources 중 하나를 화면 권한으로 가졌다         → 컬렉션 전체 (owner_only 제외)
  ⓓ 분석 컬렉션이고 ⓐ~ⓒ 가 아니면                                   → 청크의 required_resource(그 산출물을 보여 주는 화면 API 리소스)를
                                                                      가진 청크만 (화면 API 권한과 같은 결과 — ACL-05)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from nhdip.models import KbCollection, Setting

AUDIENCES = ("all", "restricted", "owner_only")
KINDS = ("document", "analysis", "glossary", "catalog")
UNASSIGNED = "analysis.unassigned"
ARTIFACT_KINDS = ("analysis", "glossary", "catalog")  # 산출물 청크(kb_chunk)를 갖는 컬렉션 종류


@dataclass
class CollectionInfo:
    code: str
    label: str
    kind: str
    owner_orgs: list[str] = field(default_factory=list)
    shared_orgs: list[str] = field(default_factory=list)
    required_resources: list[str] = field(default_factory=list)
    audience: str = "restricted"
    sources: dict[str, Any] = field(default_factory=dict)
    boost: float = 0.0
    sort: int = 0

    def doc_classes(self) -> list[str]:
        return [str(x) for x in (self.sources.get("doc_classes") or [])]


@dataclass
class AccessContext:
    """질문하는 사용자의 접근 정보 — HTTP 계층(api)이 만들어 넘긴다."""

    emp_no: str | None = None
    is_admin: bool = False
    org_codes: set[str] = field(default_factory=set)  # 사용자 조직 + 모든 상위 조직
    resources: set[str] | None = field(default_factory=set)  # 화면 API 리소스 (None = 제한 없음)
    offices: set[str] | None = None  # 열람 가능한 지점(사무소) 코드 (None = 제한 없음)
    dept_docs: set[str] | None = None  # 열람 가능한 부서한정 문서 코드 (None = 제한 없음)
    screen: str | None = None  # 지금 보고 있는 화면 경로 (가산점 힌트)
    # 영업점 공통 — 사업부서가 '영업점 참고'로 연 수행방안의 연결 자료(views.plan_share.branch_grant). 위 규칙과 별도로 더 연다.
    # 값 = 그 자료를 연 수행방안 id ('' = 영업점 참고 요약). 질문할 때마다 지금 원장에서 만든다 — 다시 계산한 결과가 그대로 이어진다
    grant_sources: dict[str, str] | None = None  # 산출물 키(청크 source_key)
    grant_docs: dict[str, str] | None = None  # 문서 코드
    grant_datasets: dict[str, str] | None = None  # 데이터셋 코드(집계 도구)
    grant_label: str = "영업점 공통"
    grant_path: str = "/branch/shared"  # 공유 보고서 화면 주소 앞부분('/{수행방안 id}' 를 붙인다)


@dataclass
class AccessScope:
    ctx: AccessContext
    collections: dict[str, CollectionInfo]  # 접근 가능한(전체 또는 일부) 컬렉션
    full: list[str]  # 컬렉션 전체 열람
    gated: list[str]  # 청크 단위(required_resource)로만 열람
    owned: set[str]  # 담당 팀인 컬렉션
    doc_classes: list[str] | None  # 열람 가능한 문서 분류 (None = 제한 없음)
    doc_owned_classes: set[str] = field(default_factory=set)
    granted: list[str] = field(default_factory=list)  # 영업점 공통 연결 자료(grant_sources)로만 열리는 컬렉션 — 그 산출물 청크만

    def label(self, code: str) -> str:
        c = self.collections.get(code)
        return c.label if c else code

    def has_analysis(self) -> bool:
        return bool(self.full or self.gated or self.granted)

    def granted_source(self, key: str | None) -> str | None:
        """영업점 공통으로 열린 청크면 그 수행방안 id('' = 영업점 참고 요약), 아니면 None — 내 권한으로도 열리는 컬렉션이면 None."""
        g = self.ctx.grant_sources
        if not g or not key:
            return None
        return g.get(key)

    def public(self) -> list[dict[str, Any]]:
        """응답용 — 내가 질문할 수 있는 컬렉션 (권한 밖은 없음). 영업점 공통으로만 열린 컬렉션은 shared 표시."""
        out = []
        for code in [*self.full, *self.gated, *self.granted]:
            c = self.collections[code]
            out.append({"code": c.code, "label": c.label, "kind": c.kind, "owned": code in self.owned, "partial": code not in self.full, **({"shared": True} if code in self.granted else {})})
        return sorted(out, key=lambda x: (self.collections[x["code"]].sort, x["code"]))

    def scope_keys(self) -> list[str] | None:
        if self.ctx.is_admin or self.ctx.offices is None:
            return None
        return sorted(f"office:{o}" for o in self.ctx.offices)


# ── 컬렉션 읽기 ───────────────────────────────────────────────
def _orgs(v: Any) -> list[str]:
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else []


def to_info(row: KbCollection) -> CollectionInfo:
    return CollectionInfo(
        code=row.code, label=row.label, kind=row.kind or "analysis", owner_orgs=_orgs(row.owner_orgs), shared_orgs=_orgs(row.shared_orgs),
        required_resources=_orgs(row.required_resources), audience=row.audience if row.audience in AUDIENCES else "restricted",
        sources=dict(row.sources or {}) if isinstance(row.sources, dict) else {}, boost=float(row.boost or 0.0), sort=int(row.sort or 0),
    )


def load_collections(session: Session, *, enabled_only: bool = True) -> list[CollectionInfo]:
    q = select(KbCollection).order_by(KbCollection.sort, KbCollection.code)
    if enabled_only:
        q = q.where(KbCollection.enabled)
    return [to_info(r) for r in session.execute(q).scalars()]


# ── 접근 범위 해석 ────────────────────────────────────────────
def _reachable(session: Session, ctx: AccessContext, gated: list[str]) -> list[str]:
    """청크 단위 열람 컬렉션 중 내 화면 리소스(·지점 범위)로 열 수 있는 청크가 하나라도 있는 것."""
    if not ctx.resources:
        return []
    sql = "SELECT DISTINCT collection_code FROM app.kb_chunk WHERE collection_code = ANY(CAST(:g AS text[])) AND required_resource = ANY(CAST(:r AS text[]))"
    params: dict[str, Any] = {"g": gated, "r": sorted(ctx.resources)}
    if ctx.offices is not None:
        sql += " AND (scope_key IS NULL OR scope_key = ANY(CAST(:s AS text[])))"
        params["s"] = sorted(f"office:{o}" for o in ctx.offices)
    hit = set(session.execute(text(sql), params).scalars())
    return [g for g in gated if g in hit]


def _granted(session: Session, ctx: AccessContext, have: set[str], by_code: dict[str, CollectionInfo]) -> list[str]:
    """영업점 공통 연결 산출물(grant_sources)의 청크가 든 컬렉션 가운데 내 권한으로는 열리지 않는 것 — 그 산출물 청크만 연다(kb_filter).
    꺼진 컬렉션 · 미분류 컬렉션에 든 청크도 연결 산출물이면 연다(컬렉션 규칙이 없어도 수행방안 연결이 권한이다)."""
    keys = sorted(ctx.grant_sources or {})
    if not keys:
        return []
    sql = "SELECT DISTINCT collection_code FROM app.kb_chunk WHERE source_key = ANY(CAST(:k AS text[]))"
    params: dict[str, Any] = {"k": keys}
    if ctx.offices is not None:
        sql += " AND (scope_key IS NULL OR scope_key = ANY(CAST(:s AS text[])))"
        params["s"] = sorted(f"office:{o}" for o in ctx.offices)
    out = []
    for code in sorted(session.execute(text(sql), params).scalars()):
        if code in have:
            continue
        if code not in by_code:
            row = session.get(KbCollection, code)
            by_code[code] = to_info(row) if row is not None else CollectionInfo(code=code, label=ctx.grant_label, kind="analysis")
        out.append(code)
    return out


def _all_doc_classes(session: Session) -> list[str]:
    out: set[str] = set()
    for origin in ("bank", "ext"):
        out |= set(session.execute(text(f"SELECT DISTINCT doc_class FROM {origin}.document WHERE is_current")).scalars())
    return sorted(out)


def resolve_scope(session: Session, ctx: AccessContext, collections: list[CollectionInfo] | None = None) -> AccessScope:
    cols = collections if collections is not None else load_collections(session)
    by_code = {c.code: c for c in cols}
    full: list[str] = []
    gated: list[str] = []
    owned: set[str] = set()
    for c in cols:
        owner_hit = bool(set(c.owner_orgs) & ctx.org_codes)
        shared_hit = bool(set(c.shared_orgs) & ctx.org_codes)
        if owner_hit:
            owned.add(c.code)
        if ctx.is_admin or owner_hit or shared_hit or c.audience == "all":
            full.append(c.code)
        elif c.audience != "owner_only" and ctx.resources is not None and set(c.required_resources) & ctx.resources:
            full.append(c.code)
        elif c.audience != "owner_only" and c.kind in ARTIFACT_KINDS:
            gated.append(c.code)
    if gated:
        # 청크 단위로만 열 수 있는 컬렉션은 내가 열 수 있는 청크가 실제로 있을 때만 범위에 나타낸다(존재 비노출 — ACL-04)
        gated = _reachable(session, ctx, gated)
    granted = _granted(session, ctx, set(full) | set(gated), by_code) if ctx.grant_sources and not ctx.is_admin else []
    accessible = {code: by_code[code] for code in [*full, *gated, *granted]}
    # 문서 분류 — 문서 컬렉션이 가져간 분류만, '*' 는 다른 컬렉션이 가져가지 않은 나머지 분류
    doc_cols = [c for c in cols if c.kind == "document"]
    # '*' 의 나머지 계산은 꺼진 컬렉션의 분류도 '가져간 것' 으로 본다 — 끄면 그 분류가 '기타 문서(전체 공개)' 로 새지 않고 닫힌다(실패 시 닫힘)
    all_doc_cols = doc_cols if collections is not None else [c for c in load_collections(session, enabled_only=False) if c.kind == "document"]
    claimed = {x for c in all_doc_cols for x in c.doc_classes() if x != "*"}
    classes: set[str] = set()
    owned_classes: set[str] = set()
    need_all = False
    for code in full:
        c = accessible[code]
        if c.kind != "document":
            continue
        for x in c.doc_classes():
            if x == "*":
                need_all = True
                if code in owned:
                    owned_classes.add("*")
            else:
                classes.add(x)
                if code in owned:
                    owned_classes.add(x)
    if need_all:
        classes |= set(_all_doc_classes(session)) - claimed
    return AccessScope(ctx=ctx, collections=accessible, full=full, gated=gated, owned=owned, doc_classes=None if ctx.is_admin and not doc_cols else sorted(classes), doc_owned_classes=owned_classes,
                       granted=granted)


# ── SQL 사전 필터 ─────────────────────────────────────────────
def kb_filter(scope: AccessScope, alias: str = "c") -> tuple[str, dict[str, Any]]:
    """분석 결과 청크(app.kb_chunk) 사전 필터 — (SQL 조각, 바인딩)."""
    a = alias
    params: dict[str, Any] = {"kb_full": scope.full, "kb_gated": scope.gated, "kb_res": sorted(scope.ctx.resources or [])}
    parts = [f"{a}.collection_code = ANY(CAST(:kb_full AS text[]))"]
    if scope.gated and scope.ctx.resources:
        parts.append(f"({a}.collection_code = ANY(CAST(:kb_gated AS text[])) AND {a}.required_resource = ANY(CAST(:kb_res AS text[])))")
    if scope.ctx.grant_sources and not scope.ctx.is_admin:
        # 영업점 공통 — 영업점 참고 수행방안의 연결 산출물(지금 세대 청크)
        parts.append(f"{a}.source_key = ANY(CAST(:kb_grant AS text[]))")
        params["kb_grant"] = sorted(scope.ctx.grant_sources)
    sql = "(" + " OR ".join(parts) + ")"
    scopes = scope.scope_keys()
    if scopes is not None:
        sql += f" AND ({a}.scope_key IS NULL OR {a}.scope_key = ANY(CAST(:kb_scopes AS text[])))"
        params["kb_scopes"] = scopes
    return sql, params


def doc_filter(scope: AccessScope, alias: str = "d") -> tuple[str, dict[str, Any]]:
    """문서 청크 사전 필터 — 허용 문서 분류 + 부서한정 문서 (graph.evidence.doc_visible 과 같은 규칙)."""
    a = alias
    grant = sorted(scope.ctx.grant_docs or {}) if not scope.ctx.is_admin else []
    conds: list[str] = []
    params: dict[str, Any] = {}
    closed = False
    if scope.doc_classes is not None:
        if not scope.doc_classes:
            closed = True
        else:
            conds.append(f"{a}.doc_class = ANY(CAST(:doc_classes AS text[]))")
            params["doc_classes"] = scope.doc_classes
    if not closed and scope.ctx.dept_docs is not None:
        conds.append(f"(COALESCE({a}.meta->>'accessClass', 'internal') <> 'dept_only' OR {a}.doc_code = ANY(CAST(:dept_docs AS text[])))")
        params["dept_docs"] = sorted(scope.ctx.dept_docs)
    if not grant:
        return ("FALSE", {}) if closed else (" AND ".join([f"{a}.is_current", *conds]), params)
    # 영업점 공통 — 영업점 참고 수행방안의 연결 근거 문서는 분류 · 부서한정과 별도로 연다(현재 판만)
    params = {} if closed else params
    params["doc_grant"] = grant
    mine = "FALSE" if closed else (" AND ".join(conds) or "TRUE")
    return f"{a}.is_current AND (({mine}) OR {a}.doc_code = ANY(CAST(:doc_grant AS text[])))", params


# ── 산출물 → 컬렉션 · 화면 리소스 배정 ────────────────────────
def base_key(key: str) -> str:
    """범위 산출물 '<키>@<지점>' 의 키."""
    return key.split("@", 1)[0]


def lookup_prefix(mapping: dict[str, Any], key: str) -> Any:
    """정확히 일치 → 끝이 '.' 또는 '-' 인 접두어 중 가장 긴 것."""
    if key in mapping:
        return mapping[key]
    best = None
    for k in mapping:
        if k.endswith((".", "-")) and key.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return mapping[best] if best else None


def assign_collection(cols: list[CollectionInfo], key: str, *, persona: str | None = None, space: str | None = None) -> str:
    """산출물(또는 그 안의 단위)이 속할 컬렉션 코드 — 페르소나 → 분석 공간 → 키 정확 일치 → 키 접두어 → 미분류."""
    k = base_key(key)
    analysis = [c for c in cols if c.kind in ARTIFACT_KINDS]
    if persona:
        for c in analysis:
            if persona in (c.sources.get("personas") or []):
                return c.code
    if space:
        for c in analysis:
            if space in (c.sources.get("spaces") or []):
                return c.code
    for c in analysis:
        if k in (c.sources.get("artifact_keys") or []):
            return c.code
    best: tuple[int, str] | None = None
    for c in analysis:
        for p in c.sources.get("artifact_prefixes") or []:
            if k.startswith(p) and (best is None or len(p) > best[0]):
                best = (len(p), c.code)
    return best[1] if best else UNASSIGNED


def setting_dict(session: Session, key: str, default: dict[str, Any]) -> dict[str, Any]:
    s = session.get(Setting, key)
    return {**default, **s.value} if s is not None and isinstance(s.value, dict) else dict(default)


def screen_collections(cols: list[CollectionInfo], screen: str | None) -> set[str]:
    """현재 화면 경로에 맞는 컬렉션 (sources.screens 접두어)."""
    if not screen:
        return set()
    return {c.code for c in cols if any(screen.startswith(p) for p in (c.sources.get("screens") or []))}
