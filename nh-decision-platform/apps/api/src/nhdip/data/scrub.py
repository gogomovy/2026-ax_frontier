"""삭제한 자료의 흔적 정리 (Phase J 후속 · DEL-13~15 · Q167~Q169).

자료를 지우면 원장(행 · 청크)과 색인 · 그래프는 `deletion.py` 가 지운다. 이 모듈은 그 자료의 **내용이 복사돼 남은 곳**을 정리한다.
- 문서: 지운 청크 본문의 조각이 든 ① 실행 기록(`ops.llm_call` 프롬프트 · 응답, `ops.node_run` 입출력) ② 화면 산출물의 근거 조각(`evidence[].snippet`)
        ③ 그 조각이 든 옛 산출물 세대. 문서는 청크 id 를 어디에도 남기지 않으므로 **본문 일부의 일치**로 찾는다.
- 데이터셋: 지운 자료로 계산된 옛 산출물 세대 — 삭제로 다시 계산한 워크플로우가 한 번 끝난 뒤에 지난 세대만 지운다(`purge_task` store=pg).

지우는 것은 내용뿐이다 — 호출 기록의 토큰 · 비용 · 시각 · 상태 같은 메타는 남긴다. 지운 자리에는 지웠다는 표시가 남는다.
계산 기록(`calc.calc_run` · `calc.metric_value`)은 요구사항 CALC-02 의 불변 기록이라 지우지 않는다 — 대신 다른 지표가 쓰지 못하게 막는다(calc/metrics `_from_deleted_data`).
감사 로그는 건드리지 않는다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from nhdip.models import Metric, ViewArtifact, ViewBinding, Workflow, WorkflowRun, utcnow

log = logging.getLogger(__name__)

SNIPPET_LEN = 40  # 일치 검사에 쓰는 본문 조각 길이
SNIPPET_MIN = 14  # 이보다 짧은 조각은 우연히 겹칠 수 있어 쓰지 않는다
SNIPPETS_PER_TEXT = 2
SNIPPETS_MAX = 600
BATCH = 40  # 한 질의에 넣는 패턴 수
SCRUBBED = "[삭제된 자료의 내용 — 제거됨]"
WAIT_MAX = timedelta(hours=24)  # 삭제 뒤 재계산을 기다리는 최대 시간


class NotReady(ValueError):
    """삭제 뒤 관련 워크플로우가 아직 다시 끝나지 않음 — 정리 작업을 대기로 두고 다시 시도한다."""


# ═════════════════════════ 본문 조각 ═════════════════════════
def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def snippets_of(texts: list[str]) -> list[str]:
    """청크 본문 → 다른 곳에 복사된 흔적을 찾을 짧은 조각들.

    호출 기록 · 산출물은 JSON 이라 따옴표 · 역슬래시 · 줄바꿈이 이스케이프된다 — 그런 글자를 만나면 끊어서 이스케이프 없는 조각만 쓴다.
    프롬프트 · 근거에는 청크 앞부분(수백 자)만 들어가므로 앞 240자 안에서 고른다(첫 조각과 가장 긴 조각)."""
    out: list[str] = []
    seen: set[str] = set()
    for t in texts:
        head = (t or "")[:240]
        parts = [p.strip() for p in re.split(r'["\\\n\r\t]+', head) if len(p.strip()) >= SNIPPET_MIN]
        if not parts:
            continue
        for p in dict.fromkeys([parts[0], max(parts, key=len)][:SNIPPETS_PER_TEXT]):
            s = p[:SNIPPET_LEN]
            if s not in seen:
                seen.add(s)
                out.append(s)
        if len(out) >= SNIPPETS_MAX:
            break
    return out


def _patterns(snips: list[str]) -> list[list[str]]:
    """LIKE 패턴(와일드카드 이스케이프) 묶음 목록."""
    pats = ["%" + s.replace("%", r"\%").replace("_", r"\_") + "%" for s in snips]
    return [pats[i : i + BATCH] for i in range(0, len(pats), BATCH)]


# ═════════════════════════ 실행 기록 (llm_call · node_run) ═════════════════════════
def scrub_run_traces(session: Session, snips: list[str], since: datetime | None) -> dict[str, int]:
    """본문 조각이 든 호출 기록 · 노드 입출력의 내용을 지운다 — 토큰 · 비용 · 시각 · 상태 같은 메타는 남긴다."""
    counts = {"llmCalls": 0, "nodeRuns": 0}
    if not snips:
        return counts
    since = since or datetime(1970, 1, 1, tzinfo=utcnow().tzinfo)
    for pats in _patterns(snips):
        p = {"pats": pats, "since": since, "note": SCRUBBED}
        n = session.execute(
            text(
                "UPDATE ops.llm_call SET messages = jsonb_build_array(jsonb_build_object('role', 'system', 'content', CAST(:note AS text))), "
                "response = CASE WHEN response IS NULL THEN NULL ELSE jsonb_build_object('scrubbed', true, 'usage', response->'usage') END, "
                "output_text = CASE WHEN output_text IS NULL THEN NULL ELSE CAST(:note AS text) END "
                "WHERE created_at >= :since AND (messages::text LIKE ANY(CAST(:pats AS text[])) OR response::text LIKE ANY(CAST(:pats AS text[])) OR output_text LIKE ANY(CAST(:pats AS text[])))"
            ),
            p,
        ).rowcount
        counts["llmCalls"] += int(n or 0)
        for col in ("output", "input"):
            n = session.execute(
                text(
                    f"UPDATE ops.node_run SET {col} = jsonb_build_object('scrubbed', true, 'reason', CAST(:note AS text)) "
                    f"WHERE started_at >= :since AND {col}::text LIKE ANY(CAST(:pats AS text[]))"
                ),
                p,
            ).rowcount
            counts["nodeRuns"] += int(n or 0)
    return counts


# ═════════════════════════ 화면 산출물의 근거 조각 ═════════════════════════
def _is_evidence(d: Any) -> bool:
    return isinstance(d, dict) and isinstance(d.get("snippet"), str) and ("doc" in d or d.get("sourceKind") == "doc_chunk")


def _strip_evidence(node: Any, hit) -> int:
    """JSON 안의 근거 목록에서 지운 문서의 조각을 가진 항목을 뺀다 — 뺀 개수."""
    n = 0
    if isinstance(node, dict):
        for v in node.values():
            n += _strip_evidence(v, hit)
    elif isinstance(node, list):
        keep = [x for x in node if not (_is_evidence(x) and hit(x["snippet"]))]
        if len(keep) != len(node):
            n += len(node) - len(keep)
            node[:] = keep
        for v in node:
            n += _strip_evidence(v, hit)
    return n


def scrub_artifact_evidence(session: Session, texts: list[str], snips: list[str], since: datetime | None, actor: str | None) -> dict[str, Any]:
    """현재 산출물의 근거 목록에서 지운 문서의 조각을 빼 새 세대로 게시하고, 그 조각이 든 옛 세대를 지운 뒤 질문하기 색인을 갱신한다."""
    from nhdip.locks import lock
    from nhdip.views.store import publish

    plain = [_plain(t) for t in texts if t]

    def hit(snippet: str) -> bool:
        s = _plain(snippet)
        return len(s) >= 20 and any(s in t for t in plain)

    out: dict[str, Any] = {"evidenceRemoved": 0, "republished": [], "generationsRemoved": 0}
    if not plain:
        return out
    for row in session.execute(select(ViewArtifact).where(ViewArtifact.is_current)).scalars().all():
        import copy

        payload = copy.deepcopy(row.payload)
        removed = _strip_evidence(payload, hit)
        if not removed:
            continue
        lock(session, f"artifact:{row.key}")
        publish(session, row.key, payload, produced_by="deletion", changes=[{"artifact": row.key, "evidenceRemoved": removed}])
        out["evidenceRemoved"] += removed
        out["republished"].append(row.key)
    session.flush()
    # 그 조각이 든 옛 세대 — 방금 새 세대로 바뀐 이전 현재 세대도 여기에 든다
    for pats in _patterns(snips):
        q = text("DELETE FROM app.view_artifact WHERE NOT is_current AND created_at >= :since AND payload::text LIKE ANY(CAST(:pats AS text[]))")
        out["generationsRemoved"] += int(session.execute(q, {"pats": pats, "since": since or datetime(1970, 1, 1, tzinfo=utcnow().tzinfo)}).rowcount or 0)
    if out["republished"]:
        from nhdip.knowledge.indexer import index_artifacts

        try:
            with session.begin_nested():
                index_artifacts(session, out["republished"])  # 질문하기 색인(app.kb_chunk) — Elasticsearch 는 워커가 맞춘다
        except Exception as exc:  # noqa: BLE001 — 색인 실패가 삭제를 막지 않는다(워커 대조가 복구)
            log.warning("근거 제거 뒤 색인 갱신 실패(워커 대조가 복구): %s", exc)
            out["indexError"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out


# ═════════════════════════ 데이터셋 — 옛 산출물 세대 ═════════════════════════
def _datasets_in(args: Any) -> set[str]:
    from nhdip.graph.projection import _datasets_in_args

    return _datasets_in_args(args)


def lineage_keys(session: Session, dataset_code: str) -> set[str]:
    """이 데이터셋으로 계산되는 화면 산출물 키 — 지표(참조 지표까지) → 그 수치 id 를 가진 산출물, 바인딩(표 · 차트)의 산출물."""
    from nhdip.data.sources import Resolver

    names = Resolver(session).refs_for(dataset_code)  # 코드 + 이 자료를 가리키는 업무 구성의 자료 이름 (Phase O)
    metrics = list(session.execute(select(Metric)).scalars())
    chosen = {m.code for m in metrics if names & _datasets_in(m.args)}
    grew = True
    while grew:  # {"metric": X} 로 이어지는 지표도
        grew = False
        for m in metrics:
            if m.code not in chosen and any(isinstance(r, dict) and r.get("metric") in chosen for r in (m.args or {}).values()):
                chosen.add(m.code)
                grew = True
    fig_ids = {fid for m in metrics if m.code in chosen for fid in (m.figure_ids or [m.code])}
    keys: set[str] = set()
    import json

    for b in session.execute(select(ViewBinding)).scalars():
        blob = json.dumps(b.params or {}, ensure_ascii=False, default=str)
        if names & _datasets_in(b.params) or any(f'"{c}"' in blob for c in chosen):
            keys.add(b.artifact_key)
    if fig_ids:
        from nhdip.knowledge.render import collect_figures

        for row in session.execute(select(ViewArtifact.key, ViewArtifact.payload).where(ViewArtifact.is_current)).all():
            if set(collect_figures(row.payload)) & fig_ids:
                keys.add(row.key.split("@", 1)[0])
    return keys


def purge_artifact_history(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """삭제 뒤 다시 계산된 뒤에만 — 이 데이터셋으로 만든 산출물의 지난 세대를 지운다.

    `dataset.deleted` 가 깨우는 워크플로우(디스패처 매칭 그대로)가 삭제 뒤 한 번 끝나야 현재 세대가 새 자료 기준이 된다.
    그 전에 지우면 낡은 현재 세대가 곧 지난 세대가 되어 다시 남는다. 끝나지 않으면 대기, 24시간이 지나도 안 끝나면 건너뜀."""
    from nhdip.models import OutboxEvent
    from nhdip.workflow.dispatcher import match_event

    code, after = str(payload["dataset"]), datetime.fromisoformat(str(payload["after"]))
    ev = OutboxEvent(id=0, type="dataset.deleted", payload={"dataset": code, "origin": payload.get("origin"), "kind": payload.get("kind")})
    wfs = sorted(match_event(session, ev))
    keys = lineage_keys(session, code)
    if not wfs or not keys:
        return {"status": "skipped", "reason": "이 자료로 계산하는 워크플로우 · 산출물이 없어 정리할 이력이 없음"}
    # 산출물을 만드는 워크플로우만 기다린다 — 그래프 투영처럼 모든 삭제에 깨어나지만 산출물이 없는(outputs 가 빈) 워크플로우는 이력과 무관하다
    names = {w.code for w in session.execute(select(Workflow).where(Workflow.code.in_(wfs), Workflow.enabled)).scalars() if (w.outputs or [])}
    waiting = [
        w
        for w in sorted(names)
        if not session.execute(
            select(WorkflowRun.id).where(WorkflowRun.workflow_code == w, WorkflowRun.finished_at > after, WorkflowRun.status.in_(("succeeded", "degraded"))).limit(1)
        ).first()
    ]
    if waiting:
        if utcnow() - after > WAIT_MAX:
            return {"status": "skipped", "reason": "24시간 안에 다시 계산되지 않아 건너뜀: " + ", ".join(waiting)}
        raise NotReady("삭제 뒤 재계산 대기: " + ", ".join(waiting))
    n = 0
    for key in sorted(keys):
        res = session.execute(delete(ViewArtifact).where((ViewArtifact.key == key) | ViewArtifact.key.like(key.replace("_", r"\_") + "@%", escape="\\"), ~ViewArtifact.is_current, ViewArtifact.created_at <= after))
        n += int(res.rowcount or 0)
    return {"status": "done", "generations": n, "artifacts": sorted(keys)[:30], "workflows": sorted(names)}
