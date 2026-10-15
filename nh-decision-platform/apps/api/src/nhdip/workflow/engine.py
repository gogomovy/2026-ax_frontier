"""DB 정의 워크플로우 엔진 (AGT-01, EVT-04).

cfg.workflow_node 를 seq 순서로 실행한다. 노드마다 입력·출력·소요·오류를 ops.node_run 에 남기고,
LLM 호출은 ops.llm_call 로 연결된다. 비활성 노드는 skipped.
노드가 실패하면 config.optional=true 인 경우만 degraded 로 계속 진행한다.
산출물은 publish 노드에서만 새 세대로 교체된다(실패한 실행은 화면에 반영되지 않음).
"""
from __future__ import annotations

import copy
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.calc.metrics import EvalContext
from nhdip.models import NodeRun, Workflow, WorkflowNode, WorkflowRun, new_id, utcnow
from nhdip.scopes import llm_scopes, scope_cap, scope_spec, scope_values
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
    base: dict[str, Any] = field(default_factory=dict)  # 읽은 시점 사본 — 게시 때 3방향 병합 기준 (B.32)
    deferred: list[tuple[str, dict[str, Any], str | None]] = field(default_factory=list)  # 실행 성공 후 낼 이벤트
    # 범위 산출물('<키>@<범위>', B.47) — 노드가 보는 산출물에서는 빼 둔다(기본 범위 수치 · 서술이 다른 지점 산출물을 덮지 않게)
    scoped_artifacts: dict[str, Any] = field(default_factory=dict)
    # 이 범위 실행에서 LLM 을 쓰지 않는 사유(BRM-07 · 범위 서술 상한) — 변화 판단 · 플래너는 규칙, 서술은 기존 문장 유지
    llm_off: str | None = None

    def load_artifacts(self) -> dict[str, Any]:
        if not self.artifacts:
            current = all_current(self.session)
            self.base = copy.deepcopy(current)
            self.artifacts = {k: v for k, v in current.items() if "@" not in k}
            self.scoped_artifacts = {k: v for k, v in current.items() if "@" in k}
        return self.artifacts

    def emit_after_success(self, type_: str, payload: dict[str, Any], actor: str | None = None) -> None:
        """실행이 성공(게시 완료)한 뒤에만 낼 이벤트 — 실패한 실행의 변화가 다른 워크플로우를 깨우지 않도록 (B.32).
        게시 노드가 자기 트랜잭션 안에서 내보낸다(flush_deferred) — 게시와 이벤트가 함께 커밋된다(B.33). 게시 노드가 없으면 실행 끝에."""
        self.deferred.append((type_, payload, actor))

    def flush_deferred(self) -> int:
        from nhdip.events import emit

        n = len(self.deferred)
        for type_, payload, actor in self.deferred:
            emit(self.session, type_, payload, actor)
        self.deferred = []
        return n


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


def _run_nodes(ctx: RunContext, nodes: list[WorkflowNode], summary: dict[str, Any], key_suffix: str = "") -> bool:
    """노드를 차례로 실행 — (degraded 여부). 선택 아닌 노드가 실패하면 RuntimeError."""
    session = ctx.session
    degraded = False
    for node in nodes:
        nr = NodeRun(id=new_id(), workflow_run_id=ctx.run.id, seq=node.seq, node_key=f"{node.key}{key_suffix}"[:60], impl=node.impl, agent_code=node.agent_code, status="running", input=_summ({"config": node.config}))
        ctx.node_run_id = nr.id
        t0 = time.monotonic()
        optional = bool((node.config or {}).get("optional"))
        # 선택 노드가 중간에 실패해도 그 노드가 메모리에 남긴 변경(게시 대상 · 후속 이벤트 · 상태)이 게시되지 않게 되돌린다 — DB 는 rollback 으로 이미 되돌아간다
        snap = (set(ctx.changed), list(ctx.changes), dict(ctx.state), len(ctx.deferred)) if optional else None
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
                if snap is not None:
                    ctx.changed, ctx.changes = snap[0], snap[1]
                    ctx.state.clear()
                    ctx.state.update(snap[2])
                    del ctx.deferred[snap[3] :]
        nr.finished_at = utcnow()
        nr.duration_ms = int((time.monotonic() - t0) * 1000)
        session.add(nr)
        summary["nodes"].append({"key": f"{node.key}{key_suffix}", "status": nr.status, "ms": nr.duration_ms})
        failed_required = nr.status == "failed" and not optional
        try:
            session.commit()
        except Exception as exc:  # noqa: BLE001 — 노드 기록 저장 실패(JSON 직렬화 · 열 크기 · 벡터 차원 등): 어느 노드가 왜 실패했는지 남기고 실패로 처리
            session.rollback()
            nr = NodeRun(id=new_id(), workflow_run_id=ctx.run.id, seq=node.seq, node_key=f"{node.key}{key_suffix}"[:60], impl=node.impl, agent_code=node.agent_code, status="failed",
                         input=_summ({"config": node.config}), error=f"결과 저장 실패: {type(exc).__name__}: {str(exc)[:500]}", finished_at=utcnow(), duration_ms=int((time.monotonic() - t0) * 1000))
            session.add(nr)
            session.commit()
            summary["nodes"][-1]["status"] = "failed"
            failed_required = not optional
        if failed_required:
            raise RuntimeError(f"노드 실패: {node.key}{key_suffix} — {(nr.error or '').splitlines()[0] if nr.error else ''}")
        if nr.status in ("degraded", "failed"):
            degraded = True
    return degraded

# ═════════════════════════ 범위 실행 (B.47 · 다지점) ═════════════════════════
# 설정 workflow.scopes = {워크플로우: {rule, list, key, requires[], max, shared_keys[], placeholder}}.
# 기본 범위(규칙 key 값, 예: BRANCH_SCOPE.office_code)는 이전과 똑같이 실행하고 기존 산출물 키에 게시한다.
# 목록(rule.list)의 다른 값마다 게시 전 노드를 한 번 더 돌리고 — 규칙 값 덮어쓰기 · 지표 값 '@범위' 저장 —
# 산출물은 '<키>@<범위>' 로 모아 마지막 게시 노드가 한꺼번에 게시한다. 공유 산출물(변화 피드)은 키 그대로.


def _scope_template(payload: Any, placeholder: str) -> Any:
    """기본 범위 산출물을 새 범위의 출발점으로 — 서술(인사이트 문장)은 그 범위에서 다시 쓰기 전까지 안내 문구로."""
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            # 기본 범위의 에이전트 문장은 이 범위 것이 아니다 — 표시를 떼서 이 범위 수치로 규칙 문장(서식 문구)이 다시 렌더되게
            for k in [k for k in cur if k.endswith("By") and cur[k] == "llm"]:
                del cur[k]
            if str(cur.get("id", "")).startswith("ins-") and "statement" in cur and "statementTpl" not in cur:
                cur["statement"] = placeholder
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return payload


def _missing_scope_data(ctx: RunContext, spec: dict[str, Any], value: str) -> str | None:
    for req in spec.get("requires") or []:
        try:
            _, rows, _ = ctx.eval.dataset(req["dataset"])
        except Exception as exc:  # noqa: BLE001
            return f"{req['dataset']}: {exc}"
        col = req.get("column")
        if not any(str(r.get(col)) == value for r in rows):
            return f"{req['dataset']} 에 {value} 자료 없음"
    return None


def _run_scope(ctx: RunContext, nodes: list[WorkflowNode], spec: dict[str, Any], value: str, summary: dict[str, Any], llm_off: str | None = None) -> dict[str, Any]:
    """추가 범위 한 번 — 게시 전 노드만. 결과 산출물은 ctx(기본 범위)의 '<키>@<값>' 로 옮긴다. 실패해도 실행 전체는 멈추지 않는다.
    llm_off 가 있으면 이 범위는 LLM 을 쓰지 않는다(범위 서술 상한 — 다음 실행에서 차례가 온다)."""
    suffix = f"@{value}"
    reason = _missing_scope_data(ctx, spec, value)
    if reason:
        return {"value": value, "status": "skipped", "reason": reason}
    arts_all = ctx.load_artifacts()
    shared = set(spec.get("shared_keys") or ["change_feed"])
    placeholder = str(spec.get("placeholder") or "이 범위의 의견은 다음 서술 실행 후 표시됩니다.")
    sa: dict[str, Any] = {}
    for k in ctx.workflow.outputs or []:
        if (k + suffix) in ctx.scoped_artifacts:
            sa[k] = ctx.scoped_artifacts[k + suffix]
        elif k in arts_all:
            sa[k] = _scope_template(copy.deepcopy(arts_all[k]), placeholder)
    if not sa:
        return {"value": value, "status": "skipped", "reason": "기본 범위 산출물이 없어 새 범위를 만들 수 없음"}
    for k in shared:
        if k in arts_all:
            sa[k] = arts_all[k]
    saved = (ctx.eval, ctx.artifacts, ctx.changed, ctx.changes, ctx.state, ctx.base)
    n_deferred = len(ctx.deferred)
    ctx.eval = EvalContext(session=ctx.session, workflow_run_id=ctx.run.id, rows=saved[0].rows, used_versions=saved[0].used_versions,
                           rule_overrides={spec["rule"]: {spec["key"]: value}}, scope_suffix=suffix)
    ctx.artifacts, ctx.changed, ctx.changes, ctx.state, ctx.base = sa, set(), [], {}, {}
    ctx.llm_off = llm_off
    status, err = "succeeded", None
    try:
        if _run_nodes(ctx, nodes, summary, key_suffix=suffix):
            status = "degraded"
    except Exception as exc:  # noqa: BLE001 — 한 범위가 실패해도 다른 범위 · 기본 범위 게시는 계속
        ctx.session.rollback()
        status, err = "failed", str(exc)[:500]
    scoped_changed, scoped_changes = ctx.changed, ctx.changes
    ctx.eval, ctx.artifacts, ctx.changed, ctx.changes, ctx.state, ctx.base = saved
    ctx.llm_off = None
    if status == "failed":
        del ctx.deferred[n_deferred:]  # 실패한 범위의 변화 이벤트는 내지 않는다
        return {"value": value, "status": status, "error": err, "llm": llm_off is None}
    moved = []
    for k in sorted(scoped_changed):
        dst = k if k in shared else k + suffix
        arts_all[dst] = sa[k]
        ctx.changed.add(dst)
        moved.append(dst)
    for c in scoped_changes:
        if c.get("artifact") not in shared:
            c["artifact"] = f"{c.get('artifact')}{suffix}"
    ctx.changes += scoped_changes
    return {"value": value, "status": status, "artifacts": moved, "llm": llm_off is None, **({"llmOff": llm_off} if llm_off else {})}


NO_DATA_NOTE = "올린 자료가 없어 계산하지 않음 — 화면 산출물을 값 없는 틀로 둠(자료를 올리면 자동으로 다시 계산)"


def workflow_has_data(session: Session, wf: Workflow) -> bool:
    """이 워크플로가 읽는 자료(지표 · 바인딩 · 흐름 조건의 데이터셋)에 현재 판이 하나라도 있는지.

    다른 부서 자료만 남아 있어도 이 흐름의 자료를 모두 지웠다면 '자료 없음'으로 본다 — 규칙 · 상수만으로 나오는 수치나
    지운 자료로 낸 옛 값이 화면 · 정의서 · 파이프라인에 남지 않게. 마스터(코드표)만 남은 경우도 자료 없음. 읽는 데이터셋이 없는 흐름은 전체 기준."""
    from nhdip.data.sources import Resolver
    from nhdip.graph.projection import _datasets_in_args, has_uploaded_data
    from nhdip.models import Metric, ViewBinding, WorkflowTrigger, source

    refs: set[str] = set()
    for m in session.execute(select(Metric).where(Metric.workflow_code == wf.code, Metric.enabled)).scalars():
        refs |= _datasets_in_args(m.args)
    for b in session.execute(select(ViewBinding).where(ViewBinding.workflow_code == wf.code, ViewBinding.enabled)).scalars():
        refs |= _datasets_in_args(b.params)
    for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == wf.code, WorkflowTrigger.enabled, WorkflowTrigger.kind.in_(("dataset", "master")))).scalars():
        if t.target and t.target != "*":
            refs.add(t.target)
    if not refs:
        return has_uploaded_data(session)
    res = Resolver(session)
    found = {d.code: d for d in (res.resolve(r) for r in refs) if d is not None}
    business = [d for d in found.values() if d.kind != "master"] or list(found.values())
    for d in business:
        t = source(d.origin)
        if session.execute(select(t.version.id).where(t.version.dataset_code == d.code, t.version.is_current).limit(1)).first():
            return True
    return False


def blank_outputs(session: Session, wf: Workflow, run: WorkflowRun) -> WorkflowRun:
    """올린 자료(현재 데이터셋 버전 · 현재 문서)가 하나도 없을 때 (M.23 · DEL-17 · Q210) — 계산하지 않고 이 워크플로의 화면 산출물을 값 없는 틀로 둔다.

    자료를 모두 지운 뒤 정기 실행 · 수동 실행 · 삭제 뒤 재계산이 돌아도 규칙 · 상수만으로 나오는 수치(목표 · 비율 하한)나
    지운 자료로 계산했던 옛 값이 화면에 다시 채워지지 않게 한다. 범위 산출물('<키>@<범위>')도 같이 비운다."""
    from nhdip.models import ViewArtifact, ViewBinding
    from nhdip.views.store import publish
    from nhdip.views.template import to_template

    binds = [{"artifact_key": b.artifact_key, "path": b.path} for b in session.execute(select(ViewBinding)).scalars()]
    blanked: list[str] = []
    for key in sorted(set(wf.outputs or [])):
        rows = session.execute(select(ViewArtifact).where(ViewArtifact.is_current, (ViewArtifact.key == key) | ViewArtifact.key.like(key.replace("_", r"\_") + "@%", escape="\\"))).scalars().all()
        for row in rows:
            tpl = to_template(key, row.payload, binds)
            if tpl == row.payload:
                continue
            publish(session, row.key, tpl, produced_by=wf.code, workflow_run_id=run.id, changes=[{"artifact": row.key, "blanked": "올린 자료 없음"}])
            blanked.append(row.key)
    # 정의서 표(mart.*) · 대조 결과 — 지운 자료로 적재한 행이 [컬럼 정의서] · [파이프라인]에 남지 않게
    from nhdip.contracts.materialize import clear_contract_outputs

    contracts = clear_contract_outputs(session, [wf.code])
    run.status = "succeeded"
    run.summary = {"nodes": [], "published": blanked, "figure_changes": 0, "no_data": True, "note": NO_DATA_NOTE, "contractsCleared": contracts}
    run.finished_at = utcnow()
    session.commit()
    if blanked:
        from nhdip.knowledge.indexer import index_artifacts

        try:
            index_artifacts(session, blanked)  # 자료가 없으면 색인에서 빠진다 — Elasticsearch 는 워커 대조가 맞춘다
            session.commit()
        except Exception:  # noqa: BLE001 — 색인 실패가 실행을 실패로 만들지 않는다(워커 대조가 복구)
            session.rollback()
    return run


def run_workflow(session: Session, workflow_code: str, causes: list[Any], job_id: int | None = None) -> WorkflowRun:
    import nhdip.workflow.nodes  # noqa: F401  (노드 구현 등록)

    wf = session.get(Workflow, workflow_code)
    if not wf:
        raise ValueError(f"워크플로우 없음: {workflow_code}")
    run = WorkflowRun(id=new_id(), workflow_code=wf.code, job_id=job_id, status="running", causes=causes)
    session.add(run)
    session.commit()
    if (wf.outputs or []) and not workflow_has_data(session, wf):
        return blank_outputs(session, wf, run)
    ctx = RunContext(session=session, run=run, workflow=wf, causes=causes, eval=EvalContext(session=session, workflow_run_id=run.id))
    summary: dict[str, Any] = {"nodes": []}
    try:
        # 준비 단계도 이 try 안에 둔다 — 여기서 예외가 나면 이미 저장한 'running' 실행이 영원히 열려 있게 된다
        nodes = session.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == wf.code).order_by(WorkflowNode.seq)).scalars().all()
        spec = scope_spec(session, wf.code)
        listed = scope_values(session, spec, limit=False)[1] if spec else []
        cap = scope_cap(spec) if spec else 0
        extras, dropped = listed[:cap], listed[cap:]
        pub = next((i for i, n in enumerate(nodes) if n.impl == "publish"), len(nodes)) if extras else len(nodes)
        degraded = _run_nodes(ctx, nodes[:pub], summary)
        if dropped:
            # 상한(BRM-07) 밖 범위는 계산하지 않고 실행 요약 · 운영 알림에 남긴다
            from nhdip.alerts import raise_alert

            summary["scopes_dropped"] = dropped
            raise_alert(session, "scope_limit", "warning", f"{wf.code} 범위 상한({spec.get('max', 20)}) 초과 — {len(dropped)}곳 계산 안 함",
                        {"workflow": wf.code, "max": spec.get("max", 20), "dropped": dropped}, f"scope_limit:{wf.code}:{','.join(dropped)}"[:200])
            session.commit()
        if extras:
            # 추가 범위(다지점) — 게시 전 노드를 범위마다 다시 돌리고, 게시는 아래에서 한 번에
            # LLM 을 쓸 범위는 상한(narrate_max)까지 — 서술이 오래된 범위부터 차례로 (BRM-07)
            n_llm = spec.get("narrate_max", 5)
            with_llm = set(llm_scopes(session, wf.code, extras, n_llm))
            off = f"범위 서술 상한({n_llm}곳/실행) 밖 — 규칙 판단 · 기존 문장 유지, 다음 실행에서 차례로 갱신"
            scopes = [_run_scope(ctx, nodes[:pub], spec, v, summary, None if v in with_llm else off) for v in extras]
            summary["scopes"] = scopes
            degraded = degraded or any(s["status"] in ("failed", "degraded") for s in scopes)
            degraded = _run_nodes(ctx, nodes[pub:], summary) or degraded
        run.status = "degraded" if degraded else "succeeded"
        if ctx.deferred:
            ctx.flush_deferred()
            session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        run = session.get(WorkflowRun, run.id)
        run.status = "failed"
        run.error = str(exc)[:4000]
    if run.status == "failed":
        # 실패한 실행은 아무것도 게시하지 않았다 — 메모리에만 있던 변경은 '게시됨'이 아니라 '반영 안 됨'으로 남긴다(관리자 화면이 실패를 성공으로 오해하지 않게)
        summary["published"] = []
        summary["unpublished"] = sorted(ctx.changed)
    else:
        summary["published"] = sorted(ctx.changed)
    summary["figure_changes"] = len(ctx.changes)
    missing = [str(c) for c in (ctx.state.get("missing_datasets") or [])]
    if missing:
        # 정상 상태인 '자료가 아직 없음'을 오류처럼 보이지 않게 — 어떤 자료를 기다리는지 한 줄로 (관리자 화면이 그대로 보여 준다)
        summary["missing_datasets"] = missing
        summary["note"] = "필요 자료 미업로드: " + ", ".join(missing[:8]) + (f" 외 {len(missing) - 8}건" if len(missing) > 8 else "")
    run.summary = summary
    run.finished_at = utcnow()
    session.commit()
    return run