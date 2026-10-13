"""업로드 자료 삭제 (Phase J · DEL-01~08 · 설계 §26 · Q143~Q147).

데이터 관리자가 업로드한 데이터셋 버전 · 문서를 지운다.
- PostgreSQL(원장): 같은 트랜잭션에서 행(row_store) · 본문 · 청크(pgvector 임베딩 · 전문 검색) · 추출 결과 · 추출 이슈를 지우고,
  버전/문서 행은 삭제 표시(status=deleted · deleted_at/by · delete_reason)로 남긴다 — 버전 번호 재사용 방지 · 감사 추적 (Q145).
- 현재 버전을 지우면 같은 기준일 구획(문서는 같은 문서 코드)의 직전 버전을 현재로 올린다 — 업로드 전 상태로 돌아간다 (Q144).
- 원본 파일: 커밋 뒤 다른 버전 · 문서 · 자료 요청이 같은 파일을 쓰지 않으면 지운다(내용 주소 저장이라 같은 내용은 같은 경로).
- Elasticsearch 색인 · Neo4j 그래프: 삭제 작업(ops.purge_task)을 남기고 커밋 뒤 바로 한 번, 이후 워커가 끝날 때까지 다시 시도한다 (Q146).
  현재 자료가 바뀌면 `dataset.deleted` · `document.deleted` 이벤트로 관련 워크플로우(계산 · 화면 · 그래프 재투영)가 다시 돈다.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.events import audit, emit
from nhdip.models import Dataset, ExtractionIssue, PurgeTask, UploadRequest, source, utcnow

log = logging.getLogger(__name__)
DELETED = "deleted"
REASON_MIN, REASON_MAX = 2, 500


class DeleteError(ValueError):
    """삭제할 수 없는 대상 · 요청 (HTTP 409/422)."""


@dataclass
class DeleteResult:
    kind: str  # dataset_version | document
    ref: str
    was_current: bool
    promoted: dict[str, Any] | None = None
    removed: dict[str, int] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    purge_ids: list[int] = field(default_factory=list)
    event_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "wasCurrent": self.was_current, "promoted": self.promoted, "removed": self.removed, "purgeTasks": self.purge_ids, "event": self.event_id}


def clean_reason(reason: str | None) -> str:
    r = " ".join((reason or "").split())
    if len(r) < REASON_MIN:
        raise DeleteError(f"삭제 사유를 {REASON_MIN}자 이상 입력하세요")
    return r[:REASON_MAX]


def _request_files(session: Session, kind: str, origin: str, match: dict[str, Any], marker: dict[str, Any]) -> list[str]:
    """승인된 자료 요청(UPL) 중 이 자료를 만든 요청 — 결과에 삭제 표시, 요청 원본 파일 경로를 돌려준다."""
    out: list[str] = []
    for r in session.execute(select(UploadRequest).where(UploadRequest.kind == kind, UploadRequest.origin == origin, UploadRequest.status == "approved")).scalars():
        res = r.result or {}
        if all(res.get(k) == v for k, v in match.items()):
            r.result = {**res, "deleted": marker}
            if r.file_path:
                out.append(r.file_path)
    return out


def _task(session: Session, store: str, kind: str, ref: str, payload: dict[str, Any], actor: str | None) -> PurgeTask:
    t = PurgeTask(store=store, subject_kind=kind, subject_ref=ref[:200], payload=payload, status="pending", attempts=0, result={}, created_by=actor)
    session.add(t)
    return t


# ═════════════════════════ 데이터셋 버전 ═════════════════════════
def _promote_candidate(session: Session, ds: Dataset, v: Any) -> Any | None:
    t = source(ds.origin)
    same = t.version.as_of == v.as_of if v.as_of else t.version.as_of.is_(None)
    return (
        session.execute(
            select(t.version)
            .where(t.version.dataset_code == ds.code, t.version.id != v.id, same, t.version.status.in_(("committed", "rolled_back")))
            .order_by(t.version.version.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def preview_dataset_version(session: Session, ds: Dataset, version_id: int) -> dict[str, Any]:
    """삭제 전 확인 — 현재 버전인지, 무엇이 현재 버전이 되는지, 다시 도는 워크플로우."""
    t = source(ds.origin)
    v = session.get(t.version, version_id)
    if not v or v.dataset_code != ds.code:
        raise DeleteError("버전 없음")
    nxt = _promote_candidate(session, ds, v) if v.is_current else None
    return {
        "id": v.id,
        "version": v.version,
        "status": v.status,
        "isCurrent": v.is_current,
        "asOf": v.as_of.isoformat() if v.as_of else None,
        "rows": v.row_count,
        "fileName": v.file_name,
        "promote": {"id": nxt.id, "version": nxt.version} if nxt else None,
        "emptyAfter": bool(v.is_current and not nxt),
        "event": "dataset.deleted" if v.is_current else None,
    }


def delete_dataset_version(session: Session, ds: Dataset, version_id: int, actor: str, reason: str | None, ip: str | None = None) -> DeleteResult:
    from nhdip.locks import lock

    why = clean_reason(reason)
    t = source(ds.origin)
    lock(session, f"ds:{ds.origin}:{ds.code}")  # 업로드 · 되돌리기와 같은 잠금 — 현재 버전 교체가 겹치지 않도록
    v = session.get(t.version, version_id)
    if not v or v.dataset_code != ds.code:
        raise DeleteError("버전 없음")
    if v.status == DELETED:
        raise DeleteError(f"이미 삭제된 버전입니다(v{v.version})")
    ref = f"{ds.origin}:{ds.code}:v{v.version}"
    was_current = bool(v.is_current)
    n_rows = session.execute(delete(t.row).where(t.row.version_id == v.id)).rowcount or 0
    promoted = None
    if was_current:
        nxt = _promote_candidate(session, ds, v)
        if nxt is not None:
            nxt.is_current, nxt.status, nxt.committed_at = True, "committed", utcnow()
            promoted = {"id": nxt.id, "version": nxt.version}
    now = utcnow()
    marker = {"at": now.isoformat(), "by": actor, "reason": why}
    files = [p for p in [v.file_path] if p]
    files += _request_files(session, "dataset", ds.origin, {"versionId": v.id}, marker)
    v.is_current, v.status, v.deleted_at, v.deleted_by, v.delete_reason, v.file_path = False, DELETED, now, actor, why, None
    res = DeleteResult("dataset_version", ref, was_current, promoted, {"rows": int(n_rows)}, files)
    if was_current:
        # 그래프의 버전 노드 — 재투영(이벤트)으로도 정리되지만, 저장소가 살아 있으면 바로 지운다
        task = _task(session, "neo4j", "dataset_version", ref, {"label": "DatasetVersion", "key": f"{ds.code}:v{v.version}", "dataset": ds.code, "version": v.version}, actor)
        ev = emit(session, "dataset.deleted", {"dataset": ds.code, "origin": ds.origin, "kind": ds.kind, "version": v.version, "version_id": v.id, "promoted_version": promoted["version"] if promoted else None, "rows": int(n_rows)}, actor)
        session.flush()
        res.purge_ids, res.event_id = [task.id], ev.id
    audit(session, actor, "admin.dataset.version_delete", "dataset", ds.code, {"version": v.version, "as_of": v.as_of.isoformat() if v.as_of else None, "was_current": was_current, "promoted": promoted, "rows": int(n_rows), "file": v.file_name, "reason": why}, ip)
    return res


# ═════════════════════════ 문서 ═════════════════════════
def preview_document(session: Session, origin: str, document_id: int, all_versions: bool = False) -> dict[str, Any]:
    t = source(origin)
    d = session.get(t.document, document_id)
    if not d:
        raise DeleteError("문서 없음")
    targets = _doc_targets(session, origin, d, all_versions)
    cur = any(x.is_current for x in targets)
    nxt = _doc_promote_candidate(session, origin, d.doc_code, {x.id for x in targets}) if cur else None
    chunks = session.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id.in_([x.id for x in targets]))).scalar() if targets else 0
    return {
        "id": d.id,
        "docCode": d.doc_code,
        "versions": [x.version for x in targets],
        "isCurrent": cur,
        "chunks": int(chunks or 0),
        "promote": {"id": nxt.id, "version": nxt.version} if nxt else None,
        "event": "document.deleted" if cur else None,
    }


def _doc_targets(session: Session, origin: str, d: Any, all_versions: bool) -> list[Any]:
    t = source(origin)
    if not all_versions:
        return [d] if d.status != DELETED else []
    return list(session.execute(select(t.document).where(t.document.doc_code == d.doc_code, t.document.status != DELETED).order_by(t.document.version)).scalars())


def _doc_promote_candidate(session: Session, origin: str, doc_code: str, exclude: set[int]) -> Any | None:
    t = source(origin)
    return (
        session.execute(select(t.document).where(t.document.doc_code == doc_code, t.document.status != DELETED, t.document.id.notin_(exclude or {0})).order_by(t.document.version.desc()).limit(1))
        .scalars()
        .first()
    )


def delete_document(session: Session, origin: str, document_id: int, actor: str, reason: str | None, ip: str | None = None, *, all_versions: bool = False) -> DeleteResult:
    from nhdip.knowledge import elastic
    from nhdip.locks import lock

    why = clean_reason(reason)
    t = source(origin)
    d = session.get(t.document, document_id)
    if not d:
        raise DeleteError("문서 없음")
    lock(session, f"doc:{origin}:{d.doc_code}")
    session.refresh(d)
    if d.status == DELETED and not all_versions:
        raise DeleteError(f"이미 삭제된 문서입니다({d.doc_code} v{d.version})")
    targets = _doc_targets(session, origin, d, all_versions)
    if not targets:
        raise DeleteError("지울 문서 버전이 없습니다")
    ids = [x.id for x in targets]
    was_current = any(x.is_current for x in targets)
    current_ids = [x.id for x in targets if x.is_current]
    chunk_ids = list(session.execute(select(t.chunk.id).where(t.chunk.document_id.in_(current_ids))).scalars()) if current_ids else []
    n_chunks = session.execute(delete(t.chunk).where(t.chunk.document_id.in_(ids))).rowcount or 0
    n_issues = session.execute(delete(ExtractionIssue).where(ExtractionIssue.origin == origin, ExtractionIssue.document_id.in_(ids))).rowcount or 0
    now = utcnow()
    marker = {"at": now.isoformat(), "by": actor, "reason": why}
    files: list[str] = []
    for x in targets:
        if x.file_path:
            files.append(x.file_path)
        files += _request_files(session, "document", origin, {"documentId": x.id}, marker)
    session.execute(
        update(t.document)
        .where(t.document.id.in_(ids))
        .values(is_current=False, status=DELETED, text="", extraction={}, file_path=None, deleted_at=now, deleted_by=actor, delete_reason=why)
    )
    promoted = None
    if was_current:
        nxt = _doc_promote_candidate(session, origin, d.doc_code, set(ids))
        if nxt is not None:
            nxt.is_current = True
            promoted = {"id": nxt.id, "version": nxt.version}
    ref = f"{origin}:{d.doc_code}"
    res = DeleteResult("document", ref, was_current, promoted, {"versions": len(ids), "chunks": int(n_chunks), "issues": int(n_issues)}, files)
    if was_current:
        tasks: list[PurgeTask] = []
        if chunk_ids:
            # 문서 청크 색인(현재 버전만 들어 있다) — 청크 id 는 다시 쓰이지 않으므로 그대로 지운다
            tasks.append(_task(session, "es", "document", ref, {"index": "doc", "ids": [elastic.doc_es_id(origin, c) for c in chunk_ids]}, actor))
        if promoted is None:
            # 문서 노드(키 = 출처:문서코드)와 이 문서에서만 나온 추출 개체 — 같은 코드로 다시 올리면 건너뛴다
            tasks.append(_task(session, "neo4j", "document", ref, {"label": "Document", "key": ref, "origin": origin, "doc_code": d.doc_code, "src_refs": [f"{origin}.document({i})" for i in ids]}, actor))
        ev = emit(session, "document.deleted", {"origin": origin, "document_id": d.id, "doc_code": d.doc_code, "doc_class": d.doc_class, "versions": [x.version for x in targets], "promoted_id": promoted["id"] if promoted else None}, actor)
        session.flush()
        res.purge_ids, res.event_id = [x.id for x in tasks], ev.id
    audit(session, actor, "admin.document.delete", "document", f"{origin}:{d.doc_code}", {"versions": [x.version for x in targets], "was_current": was_current, "promoted": promoted, "chunks": int(n_chunks), "reason": why}, ip)
    return res


# ═════════════════════════ 커밋 뒤 정리 ═════════════════════════
def _referenced(session: Session, path: str) -> bool:
    for origin in ("bank", "ext"):
        t = source(origin)
        if session.execute(select(t.version.id).where(t.version.file_path == path).limit(1)).first():
            return True
        if session.execute(select(t.document.id).where(t.document.file_path == path).limit(1)).first():
            return True
    # 아직 처리하지 않은(대기) 자료 요청이 같은 파일을 쓰면 남긴다
    return bool(session.execute(select(UploadRequest.id).where(UploadRequest.file_path == path, UploadRequest.status == "pending").limit(1)).first())


def remove_files(session: Session, paths: list[str]) -> dict[str, int]:
    """커밋 뒤 — 파일 저장소 안이고 아무도 쓰지 않는 원본만 지운다."""
    root = os.path.realpath(get_settings().filestore_dir)
    out = {"removed": 0, "kept": 0, "missing": 0}
    for p in dict.fromkeys(paths):
        rp = os.path.realpath(p)
        if not rp.startswith(root + os.sep):
            out["kept"] += 1
            continue
        if _referenced(session, p):
            out["kept"] += 1
            continue
        try:
            os.remove(rp)
            out["removed"] += 1
        except FileNotFoundError:
            out["missing"] += 1
        except OSError as exc:
            log.warning("원본 파일 삭제 실패 %s: %s", p, exc)
            out["kept"] += 1
    return out


def _purge_es(task: PurgeTask) -> dict[str, Any]:
    from nhdip.knowledge import elastic

    if not elastic.configured():
        return {"status": "skipped", "reason": "Elasticsearch 미구성(색인 없음)"}
    if not elastic.es_up():
        raise elastic.EsUnavailable("Elasticsearch 차단기 열림 — 다음 주기에 다시 시도")
    ids = list((task.payload or {}).get("ids") or [])
    idx = elastic.doc_index_name() if (task.payload or {}).get("index") == "doc" else elastic.index_name()
    n, bad = elastic._bulk([{"delete": {"_index": idx, "_id": i}} for i in ids], str)
    if bad:
        raise elastic.EsError(500, f"일부 삭제 실패 {len(bad)}건")
    return {"status": "done", "deleted": n, "index": idx}


def _purge_neo4j(session: Session, task: PurgeTask) -> dict[str, Any]:
    from nhdip.graph.neo4j_client import run, safe_name

    if not (get_settings().neo4j_uri or "").strip():
        return {"status": "skipped", "reason": "Neo4j 미구성"}
    p = task.payload or {}
    if task.subject_kind == "document":
        t = source(p["origin"])
        if session.execute(select(t.document.id).where(t.document.doc_code == p["doc_code"], t.document.is_current).limit(1)).first():
            return {"status": "skipped", "reason": "같은 문서 코드가 다시 올라와 현재 문서가 있음(투영이 관리)"}
    rows = run(f"MATCH (n:{safe_name(p['label'])} {{key: $key}}) WHERE n.managed = true DETACH DELETE n RETURN count(*) AS n", key=p["key"])
    out: dict[str, Any] = {"status": "done", "nodes": int(rows[0]["n"]) if rows else 0}
    refs = p.get("src_refs") or []
    if refs:
        # 이 문서에서만 나온 추출 개체 — 다른 관계가 남지 않은 관리 노드만
        orphan = run("MATCH (n) WHERE n.managed = true AND n.src_kind = 'document' AND any(r IN $refs WHERE n.src_ref STARTS WITH r) AND NOT EXISTS { (n)--() } DELETE n RETURN count(*) AS n", refs=refs)
        out["orphans"] = int(orphan[0]["n"]) if orphan else 0
    return out


def run_purge_tasks(session: Session, limit: int = 100, ids: list[int] | None = None) -> dict[str, int]:
    """대기 중인 외부 저장소 삭제 작업 — 성공하면 done, 미구성이면 skipped, 저장소 장애면 pending 유지(다음 주기)."""
    from nhdip.graph.neo4j_client import GraphUnavailable
    from nhdip.knowledge.elastic import EsUnavailable

    stats = {"done": 0, "skipped": 0, "pending": 0}
    tried: set[int] = set()
    for _ in range(limit):
        # 한 건씩 잠그고 끝나면 바로 커밋 — 상태가 곧바로 보이고, 느린 저장소가 다른 작업 · 다른 워커를 붙잡지 않는다
        q = select(PurgeTask).where(PurgeTask.status == "pending")
        if ids:
            q = q.where(PurgeTask.id.in_(ids))
        if tried:
            q = q.where(PurgeTask.id.notin_(tried))
        task = session.execute(q.order_by(PurgeTask.id).limit(1).with_for_update(skip_locked=True)).scalars().first()
        if task is None:
            break
        tried.add(task.id)
        task.attempts = (task.attempts or 0) + 1
        try:
            res = _purge_es(task) if task.store == "es" else _purge_neo4j(session, task)
        except (EsUnavailable, GraphUnavailable, OSError, ValueError) as exc:
            task.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
            stats["pending"] += 1
            session.commit()
            continue
        except Exception as exc:  # noqa: BLE001 — 한 작업의 예외가 다른 작업을 막지 않는다
            log.exception("삭제 작업 %s 실패", task.id)
            task.last_error = f"{type(exc).__name__}: {str(exc)[:400]}"
            stats["pending"] += 1
            session.commit()
            continue
        task.status, task.result, task.done_at, task.last_error = res.pop("status"), res, utcnow(), None
        stats[task.status] += 1
        session.commit()
    session.commit()
    return stats


def after_commit(session_factory: Any, files: list[str], purge_ids: list[int]) -> dict[str, Any]:
    """요청 응답 뒤(백그라운드) — 원본 파일 정리 + 삭제 작업 즉시 1회. 실패해도 워커가 다시 시도한다."""
    out: dict[str, Any] = {}
    try:
        with session_factory() as s:
            out["files"] = remove_files(s, files) if files else {}
            out["purge"] = run_purge_tasks(s, ids=purge_ids) if purge_ids else {}
    except Exception:  # noqa: BLE001
        log.exception("삭제 후 정리 실패 — 워커가 다시 시도")
    return out


def purge_status(session: Session, limit: int = 50) -> dict[str, Any]:
    rows = session.execute(select(PurgeTask).order_by(PurgeTask.id.desc()).limit(min(limit, 200))).scalars().all()
    counts = dict(session.execute(select(PurgeTask.status, func.count()).group_by(PurgeTask.status)).all())
    return {
        "counts": {k: int(v) for k, v in counts.items()},
        "tasks": [
            {"id": r.id, "store": r.store, "subjectKind": r.subject_kind, "subjectRef": r.subject_ref, "status": r.status, "attempts": r.attempts, "lastError": r.last_error, "result": r.result, "createdBy": r.created_by, "createdAt": r.created_at.isoformat() if r.created_at else None, "doneAt": r.done_at.isoformat() if r.done_at else None}
            for r in rows
        ],
    }
