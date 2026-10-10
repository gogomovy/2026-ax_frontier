"""DB 정의 워크플로우 엔진 (AGT-01, EVT-04).

cfg.workflow_node 를 seq 순서로 실행한다. 노드마다 입력·출력·소요·오류를 ops.node_run 에 남기고,
LLM 호출은 ops.llm_call 로 연결된다. 비활성 노드는 skipped.
노드가 실패하면 config.optional=true 인 경우만 degraded 로 계속 진행한다.
산출물은 publish 노드에서만 새 세대로 교체된다(실패한 실행은 화면에 반영되지 않음).
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.calc.metrics import EvalContext
from nhdip.models import NodeRun, Workflow, WorkflowNode, WorkflowRun, new_id, utcnow
from nhdip.views.store import all_current


@dataclass
class RunContext:
    session: Session
    run: WorkflowRun
    workflow: Workflow
    causes: list[Any]
    eval: EvalContext
    artifacts: dict[str, Any] = field(default_factory=dict)
    changed: set[str] = field(default_factory=set)
    changes: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    node_run_id: str | None = None

    def load_artifacts(self) -> dict[str, Any]:
        if not self.artifacts:
            self.artifacts = all_current(self.session)
        return self.artifacts


class NodeResult:
    def __init__(self, output: Any = None, status: str = "succeeded"):
        self.output = output
        self.status = status


NODE_IMPLS: dict[str, Callable[[RunContext, WorkflowNode], NodeResult]] = {}
NODE_DESCRIPTIONS: dict[str, str] = {}


def node_impl(name: str, description: str):
    def deco(fn):
        NODE_IMPLS[name] = fn
        NODE_DESCRIPTIONS[name] = description
        return fn

    return deco


def _summ(v: Any, limit: int = 20000) -> Any:
    """노드 입출력 기록용 — 너무 큰 값은 잘라 둔다."""
    import json

    try:
        s = json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"repr": repr(v)[:2000]}
    if len(s) <= limit:
        return json.loads(s)
    return {"truncated": True, "preview": s[:limit]}


def run_workflow(session: Session, workflow_code: str, causes: list[Any], job_id: int | None = None) -> WorkflowRun:
    import nhdip.workflow.nodes  # noqa: F401  (노드 구현 등록)

    wf = session.get(Workflow, workflow_code)
    if not wf:
        raise ValueError(f"워크플로우 없음: {workflow_code}")
    run = WorkflowRun(id=new_id(), workflow_code=wf.code, job_id=job_id, status="running", causes=causes)
    session.add(run)
    session.commit()
    ctx = RunContext(session=session, run=run, workflow=wf, causes=causes, eval=EvalContext(session=session, workflow_run_id=run.id))
    nodes = session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == wf.code).order_by(WorkflowNode.seq)).scalars().all()
    degraded = False
    summary: dict[str, Any] = {"nodes": []}
    try:
        for node in nodes:
            nr = NodeRun(id=new_id(), workflow_run_id=run.id, seq=node.seq, node_key=node.key, impl=node.impl, agent_code=node.agent_code, status="running", input=_summ({"config": node.config}))
            ctx.node_run_id = nr.id
            t0 = time.monotonic()
            if not node.enabled:
                nr.status = "skipped"
                nr.output = {"reason": "노드 비활성"}
            elif node.impl not in NODE_IMPLS:
                nr.status = "failed"
                nr.error = f"구현 없음: {node.impl}"
            else:
                try:
                    res = NODE_IMPLS[node.impl](ctx, node)
                    nr.status = res.status
                    nr.output = _summ(res.output)
                except Exception as exc:  # noqa: BLE001 — 노드 오류는 기록 후 판단
                    session.rollback()
                    nr.status = "failed"
                    nr.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-3000:]}"
            nr.finished_at = utcnow()
            nr.duration_ms = int((time.monotonic() - t0) * 1000)
            session.add(nr)
            summary["nodes"].append({"key": node.key, "status": nr.status, "ms": nr.duration_ms})
            if nr.status == "failed" and not (node.config or {}).get("optional"):
                session.commit()
                raise RuntimeError(f"노드 실패: {node.key} — {(nr.error or '').splitlines()[0] if nr.error else ''}")
            if nr.status in ("degraded", "failed"):
                degraded = True
            session.commit()
        run.status = "degraded" if degraded else "succeeded"
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        run = session.get(WorkflowRun, run.id)
        run.status = "failed"
        run.error = str(exc)[:4000]
    summary["published"] = sorted(ctx.changed)
    summary["figure_changes"] = len(ctx.changes)
    run.summary = summary
    run.finished_at = utcnow()
    session.commit()
    return run
