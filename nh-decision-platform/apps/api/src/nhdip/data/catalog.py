"""데이터셋 설명 카드 색인 (Phase M · 요구사항 §31 DOB-07 · Q195)

반영된 정형 자료를 AI 어시스턴트 지식 색인(app.kb_chunk → 임베딩 · Elasticsearch 동기화)에서 찾을 수 있게 설명 카드를 둔다.
카드에는 이름 · 설명 · 열 업무 이름(의미) · 기준일 · 행 수 · 담당 부서만 쓰고 값(수치)은 넣지 않는다 — 수치는 계산 커널 · 조회 도구로.
산출물 대조(knowledge.indexer)는 source_kind=artifact 만 보므로 이 카드를 지우지 않는다. 워커 주기 작업이 카드를 맞춘다(바뀐 것만).
"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, KbChunk, KbCollection, Setting

COLLECTION = "catalog.data"
KIND = "dataset"
RESOURCE = "datasets"


def _enabled(session: Session) -> bool:
    st = session.get(Setting, "knowledge.dataset_cards")
    return not (st is not None and st.value is False)


def card_text(session: Session, ds: Dataset) -> tuple[str, Any, int] | None:
    from nhdip.graph.profile import latest_profile

    from .datasets import current_versions

    vs = [v for v in current_versions(session, ds) if v.status == "committed"]
    if not vs:
        return None
    rows = sum(int(v.row_count or 0) for v in vs)
    as_of = max((v.as_of for v in vs if v.as_of), default=None)
    prof = latest_profile(session, ds.code)
    sem = ((prof.semantics or {}).get("columns") or {}) if prof is not None else {}
    cols = []
    for c in ds.columns or []:
        meaning = (sem.get(c.get("name")) or {}).get("meaning")
        label = c.get("label") or c.get("name")
        cols.append(f"{label}" + (f"({meaning})" if meaning and meaning != label else ""))
    entity = (prof.semantics or {}).get("entity") if prof is not None else None
    lines = [f"데이터셋 {ds.name} ({ds.code})", ds.description or "", f"출처: {'당행' if ds.origin == 'bank' else '외부'} · 종류: {'기준(마스터)' if ds.kind == 'master' else '실적'}" + (f" · 행이 가리키는 대상: {entity}" if entity else ""),
             "열: " + ", ".join(cols[:60])]
    if as_of:
        lines.append(f"기준일: {as_of.isoformat()}")
    lines.append("값은 AI 어시스턴트 도구(데이터 집계) · 화면 지표로 확인합니다.")
    return "\n".join(x for x in lines if x), as_of, rows


def index_dataset_cards(session: Session, codes: list[str] | None = None) -> dict[str, int]:
    """카드 맞추기 — 바뀐 카드만 다시 쓰고(같은 본문이면 그대로 · 임베딩 재사용), 지워졌거나 버전이 없는 데이터셋의 카드는 지운다."""
    out = {"inserted": 0, "kept": 0, "deleted": 0}
    if not _enabled(session) or session.get(KbCollection, COLLECTION) is None:
        # 카드를 끄거나 컬렉션이 없으면 남은 카드도 지운다(예전에는 그대로 남아 PG · Elasticsearch 에 계속 있었다) — ES 는 다음 대조가 지운다
        out["deleted"] = session.execute(delete(KbChunk).where(KbChunk.source_kind == KIND)).rowcount or 0
        session.flush()
        return out
    q = select(Dataset).where(Dataset.active)
    if codes:
        q = q.where(Dataset.code.in_(codes))
    seen: set[str] = set()
    for ds in session.execute(q).scalars():
        key = f"{KIND}:{ds.code}"
        got = card_text(session, ds)
        if got is None:
            continue
        seen.add(key)
        text, as_of, rows = got
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:40]
        cur = session.execute(select(KbChunk).where(KbChunk.source_key == key)).scalars().all()
        if len(cur) == 1 and cur[0].unit_hash == h:
            out["kept"] += 1
            continue
        for c in cur:
            session.delete(c)
        session.flush()
        # 열람 권한은 [데이터 목록] 산출물(dataset_meta)과 같은 화면 리소스 — 데이터베이스 화면 권한이 있어야 검색된다
        session.add(KbChunk(collection_code=COLLECTION, source_kind=KIND, source_key=key, unit_hash=h, ordinal=0, title=f"데이터셋 · {ds.name}"[:300], text=text,
                            required_resource=RESOURCE,
                            concepts=[], meta={"artifactTitle": ds.name, "dataset": ds.code, "rows": rows, "href": "/knowledge"}, as_of=as_of))
        out["inserted"] += 1
    if not codes:
        stale = [k for (k,) in session.execute(select(KbChunk.source_key).where(KbChunk.source_kind == KIND).distinct()).all() if k not in seen]
        if stale:
            out["deleted"] = session.execute(delete(KbChunk).where(KbChunk.source_key.in_(stale))).rowcount or 0
    session.flush()
    return out
