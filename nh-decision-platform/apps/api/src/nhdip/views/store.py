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
    from nhdip.locks import lock

    lock(session, f"artifact:{key}")  # 세대 번호 · 현재 세대 교체를 직렬화 (B.32 — 같은 트랜잭션 안에서는 다시 잡아도 된다)
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


# ── 동시 게시 병합 (B.32) ─────────────────────────────────────
_MISSING = object()


def _id_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, dict) and "id" in x for x in v)


def merge3(base: Any, ours: Any, theirs: Any) -> Any:
    """3방향 JSON 병합 — 이 실행이 읽은 시점(base) 이후 다른 실행이 게시한 내용(theirs)에 이 실행의 변경(ours)만 얹는다.

    dict 는 키별로, id 가 있는 dict 목록은 id 별로 병합한다. 같은 자리를 양쪽이 다르게 바꿨으면 이 실행(ours)이 이긴다
    (가장 최근 계산). 다른 실행이 추가한 항목은 보존된다.
    """
    if ours == base:
        return theirs
    if theirs == base or theirs is _MISSING:
        return ours
    if isinstance(ours, dict) and isinstance(theirs, dict) and isinstance(base, dict):
        out: dict[str, Any] = {}
        for k in list(theirs) + [k for k in ours if k not in theirs]:
            b, o, t = base.get(k, _MISSING), ours.get(k, _MISSING), theirs.get(k, _MISSING)
            if o is _MISSING and b is not _MISSING:
                continue  # 이 실행이 지운 키
            v = merge3(b, o, t) if o is not _MISSING else t
            if v is not _MISSING:
                out[k] = v
        return out
    if _id_list(ours) and _id_list(theirs) and _id_list(base):
        b = {x["id"]: x for x in base}
        o = {x["id"]: x for x in ours}
        out_l = []
        for t in theirs:
            i = t["id"]
            if i in b and i not in o:
                continue  # 이 실행이 지운 항목
            out_l.append(merge3(b.get(i, _MISSING), o[i], t) if i in o else t)
        seen = {x["id"] for x in out_l}
        # 이 실행이 추가한 항목 — 이 실행 목록에서 기존 항목보다 앞에 있던 것은 앞에(최신순 피드 등), 나머지는 뒤에 (B.33)
        first_old = next((k for k, x in enumerate(ours) if x["id"] in b), len(ours))
        added = [(k, x) for k, x in enumerate(ours) if x["id"] not in seen and x["id"] not in b]
        # (최대 건수 자르기는 각 노드가 다음 실행에서 다시 한다 — 여기서 자르면 양쪽이 추가한 항목을 잃는다)
        return [x for k, x in added if k < first_old] + out_l + [x for k, x in added if k >= first_old]
    return ours


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
    return (obj.get("value"), calc, obj.get("sourceRef"), obj.get("dataOrigin"), obj.get("decimals"), obj.get("unit"), obj.get("label"), repr(obj.get("basis")), repr(obj.get("align")))


def apply_basis(obj: dict[str, Any], basis: list[dict[str, Any]] | None) -> None:
    """수치의 기간 대체 표시 — 대체가 있으면 basis 를 달고 라벨의 기간 낱말('전년 동기')을 실제 견준 기간으로(원래 라벨은 labelBase),
    대체가 풀리면 원래 라벨로 되돌린다. 라벨 서식 문구(labelTpl)가 있는 수치는 render_templates 가 라벨을 다시 쓴다."""
    from .period_words import basis_list, relabel

    basis = basis_list(basis)
    if "labelBase" in obj and ("labelTpl" in obj or not basis):
        obj["label"] = obj.pop("labelBase")
    if not basis:
        obj.pop("basis", None)
        return
    obj["basis"] = basis
    if "labelTpl" in obj:
        return
    base = obj.get("labelBase") or obj.get("label")
    new = relabel(base, basis)
    if new != base:
        obj["labelBase"], obj["label"] = base, new
    elif "labelBase" in obj:
        obj["label"] = obj.pop("labelBase")


def patch_figures(obj: Any, figs: dict[str, dict[str, Any]], changes: list[dict[str, Any]], key: str = "") -> None:
    """산출물 전체에서 같은 id 의 Figure 를 모두 교체 (값 · 계산 근거 · 데이터 출처)."""
    if isinstance(obj, dict):
        if _is_figure(obj) and obj["id"] in figs:
            f = figs[obj["id"]]
            if f.get("cleared"):
                # 입력 자료가 지워졌다 — 지운 자료로 낸 옛 값 · 계산 근거를 남기지 않고 값 없는 틀로(남은 자료로 다시 계산하면 채워진다)
                from .template import strip_figure

                if obj.get("value") is not None or obj.get("stale") or obj.get("calc") or obj.get("sourceRef"):
                    before = obj.get("value")
                    strip_figure(obj)
                    obj.pop("stale", None)
                    obj.pop("staleReason", None)
                    changes.append({"artifact": key, "figure": obj["id"], "before": before, "after": None, "cleared": True, "reason": f.get("reason")})
                for v in obj.values():
                    patch_figures(v, figs, changes, key)
                return
            if f.get("stale"):
                # 계산 실패 — 값은 그대로 두고 갱신 실패 표시만 (B.32). 이전 값이 없으면(빈 상태) 표시할 '이전 값'이 없으므로 달지 않는다
                if obj.get("value") is not None and (not obj.get("stale") or obj.get("staleReason") != f.get("staleReason")):
                    obj["stale"], obj["staleReason"] = True, f.get("staleReason")
                    changes.append({"artifact": key, "figure": obj["id"], "stale": True, "reason": f.get("staleReason")})
                for v in obj.values():
                    patch_figures(v, figs, changes, key)
                return
            before = obj.get("value")
            snapshot = _trace_key(obj)
            was_stale = obj.pop("stale", None)
            obj.pop("staleReason", None)
            obj["value"] = f["value"]
            if f.get("unit") and f["unit"] != obj.get("unit"):
                obj["unit"] = f["unit"]
            if f.get("calc"):
                obj["calc"] = f["calc"]
            if f.get("sourceRef"):
                obj["sourceRef"] = f["sourceRef"]
            if f.get("dataOrigin"):
                obj["dataOrigin"] = f["dataOrigin"]
            if f.get("decimals") is not None:
                obj["decimals"] = f["decimals"]
            for k in ("verdict", "severity"):  # 판정형 수식 결과 문구 (Phase I)
                if f.get(k) is not None:
                    obj[k] = f[k]
            if "basis" in f:
                apply_basis(obj, f["basis"])
            # 비교 기간 맞춤(목표 환산 · 기간 인자) · 경영목표 수치 — 없으면 뗀다(그 달이 올라와 맞춤이 풀린 경우)
            for k in ("align", "goal"):
                if k in f:
                    if f[k]:
                        obj[k] = f[k]
                    else:
                        obj.pop(k, None)
            if before != f["value"]:
                changes.append({"artifact": key, "figure": obj["id"], "before": before, "after": f["value"]})
            elif was_stale:
                changes.append({"artifact": key, "figure": obj["id"], "before": before, "after": f["value"], "recovered": True})
            elif snapshot != _trace_key(obj):
                # 값은 같지만 계산 근거(목데이터 고정값 → 커널 계산 추적)가 바뀐 경우도 게시한다
                changes.append({"artifact": key, "figure": obj["id"], "before": before, "after": f["value"], "trace_only": True})
        for v in obj.values():
            patch_figures(v, figs, changes, key)
    elif isinstance(obj, list):
        for v in obj:
            patch_figures(v, figs, changes, key)


def _has_field(o: dict[str, Any], field: str) -> bool:
    return field in o or f"{field}Tpl" in o


def patch_insight(obj: Any, insight_id: str, fields: dict[str, Any], field: str = "statement") -> int:
    """id 가 같고 `field`(또는 그 서식 문구)를 가진 객체를 모두 고친다 — 같은 의견이 여러 산출물에 실려 있다."""
    n = 0
    if isinstance(obj, dict):
        if obj.get("id") == insight_id and _has_field(obj, field):
            obj.update(fields)
            n += 1
        for v in obj.values():
            n += patch_insight(v, insight_id, fields, field)
    elif isinstance(obj, list):
        for v in obj:
            n += patch_insight(v, insight_id, fields, field)
    return n


def find_insight(artifacts: dict[str, Any], insight_id: str, field: str = "statement") -> dict[str, Any] | None:
    """id 가 같고 `field`(서술 대상 필드 — statement · judgement · body · guideline)를 가진 첫 객체."""
    for payload in artifacts.values():
        stack = [payload]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if o.get("id") == insight_id and _has_field(o, field):
                    return o
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return None
