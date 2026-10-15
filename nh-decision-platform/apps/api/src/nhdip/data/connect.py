"""새 데이터셋 연결 도우미 (Phase M 후속 · J3.6 · 요구사항 DOB-11 · Q201)

팀이 등록한 새 자료는 정의 · 버전 · 온톨로지 · 설명 카드 · 분석 카탈로그에는 바로 들어가지만, 업무 화면 수치(지표)와
기존 워크플로(트리거)에는 관리자가 손으로 이어야 했다. 이 모듈은 이을 곳을 **추천만** 한다(연결은 관리자가 누른다).

  워크플로 추천  워크플로가 이미 읽는 데이터셋(트리거 dataset · master)과 견줘
                 ① 열 겹침(이름 · 업무 이름 · 별칭, 기준일 · 기간 같은 흔한 열 제외) ② 같은 온톨로지 객체 유형(원천 · 링크 원천)
                 ③ 같은 키 열 — 점수가 높은 순. 이미 이 자료를 읽는 워크플로는 '연결됨' 으로 따로.
  지표 · 분석    화면 수치는 지표 정의(수식 · 단위)가 있어야 하므로 자동으로 만들지 않는다. 대신 [분석 에이전트 만들기]에
                 이 자료를 골라 둔 채로 연다(글 → 정제 → 명세 → 승인 — 수치는 계산 커널).
기반 워크플로(그래프 투영 · 온톨로지 구축)는 모든 데이터셋을 이미 읽으므로 추천하지 않는다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, Metric, Workflow, WorkflowTrigger

BASE_WORKFLOWS = {"wf_graph_projection", "wf_ontology_build"}
# 어느 표에나 있는 열 — 겹쳐도 같은 업무 자료라는 근거가 되지 않는다
GENERIC = {"ym", "yyyymm", "baseym", "basedt", "asof", "date", "dt", "기준월", "기준일", "기준년월", "기준일자", "일자", "년월", "srcref", "비고", "note", "seq", "no", "번호", "istotal"}


def _norm(s: Any) -> str:
    from .datasets import _norm as norm

    return norm(s)


def column_keys(ds: Any) -> dict[str, str]:
    """{정규화 이름 · 업무 이름 · 별칭: 열 이름} — 기준일 열 · 흔한 열 제외."""
    out: dict[str, str] = {}
    for c in ds.columns or []:
        name = c.get("name")
        if not name or name == ds.as_of_column:
            continue
        for v in [name, c.get("label"), *(c.get("aliases") or [])]:
            k = _norm(v)
            if k and k not in GENERIC and len(k) >= 2:
                out.setdefault(k, name)
    return out


def ontology_classes(schema: Any, code: str) -> set[str]:
    """데이터셋이 원천인 객체 유형 + 링크 원천으로 이어지는 양 끝 유형."""
    if schema is None:
        return set()
    out = {c["label"] for c in schema.classes or [] if any(b.get("dataset") == code for b in c.get("backing") or [])}
    for r in schema.relations or []:
        if any(b.get("dataset") == code for b in r.get("backing") or []):
            out |= {r.get("from"), r.get("to")}
    return {x for x in out if x}


def _metrics_using(session: Session, code: str, names: set[str] | None = None) -> list[str]:
    from nhdip.graph.projection import _datasets_in_args

    names = names or {code}
    return [m.code for m in session.execute(select(Metric).where(Metric.enabled)).scalars() if names & _datasets_in_args(m.args)]


def connect_suggestions(session: Session, code: str, limit: int = 3) -> dict[str, Any]:
    from nhdip.data.sources import Resolver
    from nhdip.graph.projection import active_schema

    ds = session.get(Dataset, code)
    if ds is None:
        raise KeyError(code)
    res = Resolver(session)
    names = res.refs_for(code)  # 코드 + 업무 구성의 자료 이름(Phase O)
    schema = active_schema(session)
    mine = column_keys(ds)
    my_classes = ontology_classes(schema, code)
    ko = {c["label"]: c.get("ko") or c["label"] for c in (schema.classes if schema is not None else [])}
    trig = session.execute(select(WorkflowTrigger).where(WorkflowTrigger.kind.in_(["dataset", "master"]), WorkflowTrigger.enabled)).scalars().all()
    reads: dict[str, set[str]] = {}
    for t in trig:
        hit = res.resolve(t.target) if t.target != "*" else None
        reads.setdefault(t.workflow_code, set()).add(hit.code if hit is not None else t.target)
    datasets = {d.code: d for d in session.execute(select(Dataset)).scalars()}
    connected, cands = [], []
    for w in session.execute(select(Workflow).where(Workflow.enabled).order_by(Workflow.sort, Workflow.code)).scalars():
        if w.code in BASE_WORKFLOWS:
            continue
        targets = reads.get(w.code, set())
        if code in targets:
            connected.append({"workflow": w.code, "name": w.name})
            continue
        best: dict[str, Any] | None = None
        for t in sorted(targets - {"*"}):
            other = datasets.get(t)
            if other is None:
                continue
            theirs = column_keys(other)
            shared = sorted({mine[k] for k in set(mine) & set(theirs)})
            col_score = len(shared) / max(1, min(len(set(mine.values())), len(set(theirs.values()))))
            cls = sorted(my_classes & ontology_classes(schema, t))
            key_hit = bool(set(ds.key_columns or []) & set(other.key_columns or []) - {ds.as_of_column, other.as_of_column})
            score = round(min(1.0, 0.6 * col_score + (0.3 if cls else 0) + (0.1 if key_hit else 0)), 3)
            if score <= 0:
                continue
            why = []
            if shared:
                why.append(f"열 {len(shared)}개 겹침({', '.join(shared[:4])}{' 등' if len(shared) > 4 else ''}) — {other.name}")
            if cls:
                why.append("같은 온톨로지 객체: " + ", ".join(ko.get(c, c) for c in cls[:3]))
            if key_hit:
                why.append("같은 키 열")
            if best is None or score > best["score"]:
                best = {"workflow": w.code, "name": w.name, "score": score, "why": why, "via": t}
        if best is not None and best["score"] >= 0.2:
            cands.append(best)
    cands.sort(key=lambda x: (-x["score"], x["workflow"]))
    return {
        "dataset": code, "name": ds.name, "kind": ds.kind, "triggerKind": "master" if ds.kind == "master" else "dataset",
        "connected": connected, "metrics": _metrics_using(session, code, names)[:20], "suggestions": cands[:limit],
        "ontology": [{"label": c, "ko": ko.get(c, c)} for c in sorted(my_classes)],
        "builderHref": f"/analysis/builder?dataset={code}",
    }
