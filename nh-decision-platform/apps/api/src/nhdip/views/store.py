"""화면 산출물 저장소 (app.view_artifact) — 세대 교체 · 조회 · JSON 경로 패치."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from nhdip.models import ViewArtifact


def get_current(session: Session, key: str) -> Any:
    return session.execute(select(ViewArtifact.payload).where(ViewArtifact.key == key, ViewArtifact.is_current)).scalar()


def get_current_row(session: Session, key: str) -> ViewArtifact | None:
    return session.execute(select(ViewArtifact).where(ViewArtifact.key == key, ViewArtifact.is_current)).scalar()


def all_current(session: Session) -> dict[str, Any]:
    rows = session.execute(select(ViewArtifact.key, ViewArtifact.payload).where(ViewArtifact.is_current)).all()
    return {k: copy.deepcopy(p) for k, p in rows}


def publish(session: Session, key: str, payload: Any, *, produced_by: str, workflow_run_id: str | None = None, changes: list[Any] | None = None) -> ViewArtifact:
    last = session.execute(select(ViewArtifact.generation).where(ViewArtifact.key == key).order_by(ViewArtifact.generation.desc()).limit(1)).scalar()
    session.execute(update(ViewArtifact).where(ViewArtifact.key == key).values(is_current=False))
    row = ViewArtifact(
        key=key,
        generation=(last if last is not None else -1) + 1,
        is_current=True,
        payload=payload,
        produced_by=produced_by,
        workflow_run_id=workflow_run_id,
        changes=changes or [],
    )
    session.add(row)
    return row


# ── JSON 경로 ─────────────────────────────────────────────────
def get_path(obj: Any, path: str) -> Any:
    for p in path.split(".") if path else []:
        obj = obj[int(p)] if isinstance(obj, list) else obj[p]
    return obj


def set_path(obj: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    parent = get_path(obj, ".".join(parts[:-1])) if len(parts) > 1 else obj
    last = parts[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    else:
        parent[last] = value


def find_paths(obj: Any, pred, prefix: str = "") -> list[str]:
    """조건을 만족하는 dict 노드의 경로 목록 (바인딩 경로 탐색용)."""
    out: list[str] = []
    if isinstance(obj, dict):
        if pred(obj):
            out.append(prefix)
        for k, v in obj.items():
            out += find_paths(v, pred, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += find_paths(v, pred, f"{prefix}.{i}" if prefix else str(i))
    return out


# ── 수치(Figure) 패치 ─────────────────────────────────────────
def _is_figure(d: dict[str, Any]) -> bool:
    return "id" in d and "label" in d and "unit" in d and "value" in d


def _trace_key(obj: dict[str, Any]) -> Any:
    """비교용 — 실행마다 바뀌는 calcId · executedAt 은 제외."""
    calc = obj.get("calc")
    if isinstance(calc, dict):
        calc = {k: v for k, v in calc.items() if k not in ("calcId", "executedAt")}
    return (obj.get("value"), calc, obj.get("sourceRef"), obj.get("dataOrigin"), obj.get("decimals"))


def patch_figures(obj: Any, figs: dict[str, dict[str, Any]], changes: list[dict[str, Any]], key: str = "") -> None:
    """산출물 전체에서 같은 id 의 Figure 를 모두 교체 (값 · 계산 근거 · 데이터 출처)."""
    if isinstance(obj, dict):
        if _is_figure(obj) and obj["id"] in figs:
            f = figs[obj["id"]]
            before = obj.get("value")
            snapshot = _trace_key(obj)
            obj["value"] = f["value"]
            if f.get("calc"):
                obj["calc"] = f["calc"]
            if f.get("sourceRef"):
                obj["sourceRef"] = f["sourceRef"]
            if f.get("dataOrigin"):
                obj["dataOrigin"] = f["dataOrigin"]
            if f.get("decimals") is not None:
                obj["decimals"] = f["decimals"]
            if before != f["value"]:
                changes.append({"artifact": key, "figure": obj["id"], "before": before, "after": f["value"]})
            elif snapshot != _trace_key(obj):
                # 값은 같지만 계산 근거(목데이터 고정값 → 커널 계산 추적)가 바뀐 경우도 게시한다
                changes.append({"artifact": key, "figure": obj["id"], "before": before, "after": f["value"], "trace_only": True})
        for v in obj.values():
            patch_figures(v, figs, changes, key)
    elif isinstance(obj, list):
        for v in obj:
            patch_figures(v, figs, changes, key)


def patch_insight(obj: Any, insight_id: str, fields: dict[str, Any]) -> int:
    n = 0
    if isinstance(obj, dict):
        if obj.get("id") == insight_id and "statement" in obj:
            obj.update(fields)
            n += 1
        for v in obj.values():
            n += patch_insight(v, insight_id, fields)
    elif isinstance(obj, list):
        for v in obj:
            n += patch_insight(v, insight_id, fields)
    return n


def find_insight(artifacts: dict[str, Any], insight_id: str) -> dict[str, Any] | None:
    for payload in artifacts.values():
        stack = [payload]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if o.get("id") == insight_id and "statement" in o:
                    return o
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return None
