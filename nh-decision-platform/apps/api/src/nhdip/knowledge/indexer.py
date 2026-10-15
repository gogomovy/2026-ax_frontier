"""분석 결과 색인기 (요구사항 KB-01~KB-07 · 설계 §21.5).

화면 산출물(`app.view_artifact` 현재 세대)을 청크로 만들어 `app.kb_chunk` 에 동기화한다.
- 멱등: 청크 식별자는 본문 해시 — 같은 본문은 같은 행(임베딩 재사용), 바뀐 본문은 새 행, 사라진 본문은 삭제.
- 같은 게시 트랜잭션에서 호출 가능(네트워크 호출 없음). 임베딩은 maintenance 가 비동기로 채운다.
- 키별 권고 잠금(`kb:<키>`)으로 게시 중 색인과 워커 대조 색인이 겹치지 않게 한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from nhdip.analysis_registry import agent_for_tab
from nhdip.analysis_registry import space as get_space
from nhdip.graph.extraction import Resolver
from nhdip.graph.projection import active_schema
from nhdip.locks import lock
from nhdip.models import KbChunk, OrgUnit, ViewArtifact

from .access import CollectionInfo, UNASSIGNED, assign_collection, base_key, load_collections, lookup_prefix, setting_dict
from .defaults import ARTIFACT_RESOURCES, ARTIFACT_ROUTES, INDEX_DEFAULT, PERSONA_RESOURCES
from .render import render_artifact

log = logging.getLogger("nhdip.knowledge")


@dataclass
class IndexStats:
    keys: int = 0
    chunks: int = 0
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unassigned: int = 0
    empty: dict[str, int] = field(default_factory=dict)  # 청크가 0건인 산출물 {키: 세대} — 대조가 반복해서 다시 만들지 않게
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.deleted)

    def as_dict(self) -> dict[str, Any]:
        return {"keys": self.keys, "chunks": self.chunks, "inserted": self.inserted, "updated": self.updated, "deleted": self.deleted, "unassigned": self.unassigned, "errors": self.errors[:10]}


class ConceptTagger:
    """온톨로지 별칭 사전으로 본문에 나온 개념 키를 찾는다(결정론 · 네트워크 없음)."""

    def __init__(self, session: Session):
        schema = active_schema(session)
        pairs: list[tuple[str, str]] = []
        if schema is not None:
            for _label, amap in Resolver(schema).alias.items():
                for alias, key in amap.items():
                    if len(alias.replace(" ", "")) >= 2:
                        pairs.append((alias, key))
        self.pairs = sorted(set(pairs), key=lambda x: -len(x[0]))

    def tag(self, text: str) -> list[str]:
        low = (text or "").lower()
        found: list[str] = []
        for alias, key in self.pairs:
            if alias in low and key not in found:
                found.append(key)
        return found[:40]


def route_for(routes: dict[str, str], bkey: str) -> str | None:
    """산출물 키의 화면 주소 — 정확히 일치, 아니면 가장 긴 접두어('{tab}' 은 접두어 뒤 탭 키)."""
    if bkey in routes:
        return routes[bkey]
    best = None
    for k in routes:
        if k.endswith((".", "-")) and bkey.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return routes[best].replace("{tab}", bkey[len(best):]) if best else None


def _org_codes_by_name(session: Session) -> dict[str, str]:
    return {name: code for code, name in session.execute(select(OrgUnit.code, OrgUnit.name)).all()}


def index_artifacts(session: Session, keys: Iterable[str] | None = None) -> IndexStats:
    """산출물 현재 세대 → 청크 동기화. keys=None 이면 전체(대조 · 전체 재색인). 호출자가 commit 한다."""
    stats = IndexStats()
    cfg = setting_dict(session, "knowledge.index", INDEX_DEFAULT)
    resources = setting_dict(session, "knowledge.artifact_resources", ARTIFACT_RESOURCES)
    persona_res = setting_dict(session, "knowledge.persona_resources", PERSONA_RESOURCES)
    routes = setting_dict(session, "knowledge.artifact_routes", ARTIFACT_ROUTES)
    cols = load_collections(session, enabled_only=False)
    exclude = set(cfg.get("exclude_keys") or [])
    tagger = ConceptTagger(session)
    org_by_name = _org_codes_by_name(session)

    # 키 순서로 잠근다 — 게시(정렬된 키)와 같은 순서라 교착이 생기지 않는다
    q = select(ViewArtifact.key, ViewArtifact.generation, ViewArtifact.payload).where(ViewArtifact.is_current).order_by(ViewArtifact.key)
    wanted = None if keys is None else {k for k in keys}
    if wanted is not None:
        q = q.where(ViewArtifact.key.in_(sorted(wanted)))
    present: set[str] = set()
    for key, gen, payload in session.execute(q).all():
        if base_key(key) in exclude:
            continue
        present.add(key)
        stats.keys += 1
        try:
            with session.begin_nested():
                _index_one(session, key, gen, payload, cfg, cols, resources, persona_res, routes, tagger, org_by_name, stats)
        except Exception as exc:  # noqa: BLE001 — 한 산출물의 실패가 나머지를 막지 않는다(대조가 다시 시도)
            log.warning("지식 색인 실패 key=%s: %s", key, exc, exc_info=True)
            stats.errors.append(f"{key}: {type(exc).__name__}: {str(exc)[:200]}")
    # 사라졌거나 제외된 산출물의 청크 삭제
    if wanted is None:
        gone = [k for (k,) in session.execute(select(KbChunk.source_key).where(KbChunk.source_kind == "artifact").distinct()).all() if k not in present]
    else:
        gone = [k for k in wanted if k not in present]
    for k in sorted(gone):
        lock(session, f"kb:{k}")
        # 잠금을 기다리는 사이 게시된 산출물은 지우지 않는다(다음 대조가 색인) — 제외 대상은 그대로 지운다
        if base_key(k) not in exclude and session.execute(select(ViewArtifact.key).where(ViewArtifact.key == k, ViewArtifact.is_current)).first():
            continue
        stats.deleted += session.execute(delete(KbChunk).where(KbChunk.source_key == k)).rowcount or 0
    return stats


OFFICE_SCOPED_KEYS = ("branch_dashboard", "branch_tabs")


def _office_scoped(bkey: str) -> bool:
    """지점별 산출물(화면이 branch_artifact 로 지점을 검사하는 것) — 영업점 대시보드 · 분석 탭 · 영업점 보고서."""
    return bkey in OFFICE_SCOPED_KEYS or bkey.startswith("report.branch-")


def _index_one(session: Session, key: str, gen: int, payload: Any, cfg: dict[str, Any], cols: list[CollectionInfo], resources: dict[str, Any], persona_res: dict[str, Any],
               routes: dict[str, str], tagger: ConceptTagger, org_by_name: dict[str, str], stats: IndexStats) -> None:
    lock(session, f"kb:{key}")
    # 잠금을 잡은 뒤 다시 읽는다 — 기다리는 사이 게시가 끝났으면 새 세대로 색인한다(오래된 세대로 덮어쓰지 않음)
    cur = session.execute(select(ViewArtifact.generation, ViewArtifact.payload).where(ViewArtifact.key == key, ViewArtifact.is_current)).first()
    if cur is not None:
        gen, payload = cur
    bkey = base_key(key)
    scope_val = key.partition("@")[2]
    # 화면과 같은 기준 — 아직 자료로 계산되지 않은 시연 서술 · 보고서 틀은 색인하지 않는다 (M.19 · Q204)
    from nhdip.views.readiness import gate

    shown = gate(key, payload, flag=False)
    rendered = render_artifact(key, shown if shown is not None else ({} if isinstance(payload, dict) else []), cfg)
    office_code = scope_val or str((rendered.office or {}).get("code") or "")
    scope_key = f"office:{office_code}" if office_code else None
    if not office_code and _office_scoped(bkey):
        # 지점 산출물인데 지점 코드가 없으면 화면도 보여 주지 않는다(screens.branch_artifact) — 범위 없는(모든 지점 공개) 청크로 두지 않는다(실패 시 닫힘)
        rendered.drafts = []
    # 분석 에이전트 보고서(report.an-*)는 그 분석 공간의 컬렉션 · 열람 리소스 · 화면 주소
    space_key = space_resource = space_path = None
    if bkey.startswith("report.an-"):
        agent = agent_for_tab(session, bkey[len("report."):])
        sp = get_space(session, agent.space) if agent is not None else None
        if agent is not None and sp is not None:
            space_key, space_resource, space_path = agent.space, sp.get("resource"), sp.get("path")
    href = f"{space_path}/{bkey[len('report.'):]}" if space_path else route_for(routes, bkey)
    if href and scope_key:
        href += f"?office={office_code}"
    default_res = lookup_prefix(resources, bkey)

    existing = {(r.scope_key or "", r.unit_hash): r for r in session.execute(select(KbChunk).where(KbChunk.source_key == key)).scalars()}
    keep: set[tuple[str, str]] = set()
    for d in rendered.drafts:
        coll = assign_collection(cols, key, persona=d.persona, space=space_key)
        res = d.resource or (persona_res.get(d.persona) if d.persona else None) or space_resource or default_res
        fields: dict[str, Any] = dict(
            collection_code=coll, source_generation=gen, ordinal=d.ordinal, scope_key=scope_key, required_resource=res, owner_org=org_by_name.get(d.owner or ""),
            title=d.title, section_path=d.section_path, concepts=tagger.tag(d.text),
            meta={"href": href, "severity": d.severity, "artifactTitle": rendered.title, "persona": d.persona}, as_of=rendered.as_of,
        )
        ck = (scope_key or "", d.unit_hash)
        keep.add(ck)
        row = existing.get(ck)
        if row is None:
            session.add(KbChunk(source_key=key, source_kind="artifact", unit_hash=d.unit_hash, text=d.text, **fields))
            stats.inserted += 1
        else:
            dirty = False
            for name, val in fields.items():
                if getattr(row, name) != val:
                    setattr(row, name, val)
                    dirty = True
            stats.updated += 1 if dirty else 0
        if coll == UNASSIGNED:
            stats.unassigned += 1
    for ck, row in existing.items():
        if ck not in keep:
            session.delete(row)
            stats.deleted += 1
    session.flush()
    stats.chunks += len(rendered.drafts)
    if not rendered.drafts:
        stats.empty[key] = gen


def stale_keys(session: Session, empty: dict[str, int] | None = None) -> tuple[list[str], list[str]]:
    """(다시 색인할 산출물 키, 청크를 지울 키) — 현재 세대와 색인된 세대가 다르거나 색인이 없는 것."""
    cfg = setting_dict(session, "knowledge.index", INDEX_DEFAULT)
    exclude = set(cfg.get("exclude_keys") or [])
    arts = {k: g for k, g in session.execute(select(ViewArtifact.key, ViewArtifact.generation).where(ViewArtifact.is_current)).all() if base_key(k) not in exclude}
    # 산출물 청크만 대조한다 — 데이터셋 설명 카드(source_kind=dataset, Phase M · DOB-07)는 data/catalog.py 가 관리
    idx = {k: (lo, hi) for k, lo, hi in session.execute(select(KbChunk.source_key, func.min(KbChunk.source_generation), func.max(KbChunk.source_generation)).where(KbChunk.source_kind == "artifact").group_by(KbChunk.source_key)).all()}
    empty = empty or {}
    todo = [k for k, g in arts.items() if (k not in idx or idx[k] != (g, g)) and empty.get(k) != g]
    drop = [k for k in idx if k not in arts]
    return sorted(todo), sorted(drop)
