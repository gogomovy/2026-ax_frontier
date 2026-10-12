"""그래프 투영 — PostgreSQL 설정·데이터·문서 추출 결과를 Neo4j 에 멱등 MERGE (ONT-13~16, 설계 §19.3).

원칙: 사실(행 값)은 복제하지 않고 개념 노드와 계보만 둔다.
매 투영마다 세대(proj_gen)를 올리고, 이번 세대에 등장하지 않은 관리 노드·관계는 삭제한다.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.data.datasets import current_rows, current_versions
from nhdip.models import Dataset, KbChunk, Metric, OntologySchema, Workflow, WorkflowTrigger, source

from .neo4j_client import run, safe_name


def active_schema(session: Session) -> OntologySchema | None:
    return session.execute(select(OntologySchema).where(OntologySchema.active).order_by(OntologySchema.version.desc())).scalars().first()


class Batch:
    """노드·관계 수집 후 라벨/관계 유형별 UNWIND 로 일괄 반영."""

    def __init__(self, schema_version: int, gen: int, allowed_labels: set[str], allowed_rels: set[str]):
        self.sv = schema_version
        self.gen = gen
        self.allowed_labels = allowed_labels
        self.allowed_rels = allowed_rels
        self.nodes: dict[tuple[str, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
        self.rels: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        self.rejected: list[str] = []

    def node(self, labels: str | Iterable[str], key: str, props: dict[str, Any] | None = None, *, origin: str = "bank", src_kind: str = "master", src_ref: str = "", extracted_by: str = "rule"):
        labels = (labels,) if isinstance(labels, str) else tuple(labels)
        if labels[0] not in self.allowed_labels:
            self.rejected.append(f"label:{labels[0]}")
            return
        clean = {k: v for k, v in (props or {}).items() if v is not None and isinstance(v, (str, int, float, bool, list))}
        clean.update(origin=origin, src_kind=src_kind, src_ref=src_ref, extracted_by=extracted_by, schema_version=self.sv)
        self.nodes[labels][str(key)] = {**self.nodes[labels].get(str(key), {}), **clean}

    def rel(self, rtype: str, from_label: str, from_key: str, to_label: str, to_key: str, props: dict[str, Any] | None = None, *, extracted_by: str = "rule", src_ref: str = ""):
        if rtype not in self.allowed_rels:
            self.rejected.append(f"rel:{rtype}")
            return
        clean = {k: v for k, v in (props or {}).items() if v is not None and isinstance(v, (str, int, float, bool))}
        clean.update(extracted_by=extracted_by, src_ref=src_ref, schema_version=self.sv)
        self.rels[(rtype, from_label, to_label)].append({"from": str(from_key), "to": str(to_key), "props": clean})

    def flush(self) -> dict[str, int]:
        n_nodes = n_rels = 0
        for labels, items in self.nodes.items():
            lbl = ":".join(safe_name(x) for x in labels)
            rows = [{"key": k, "props": p} for k, p in items.items()]
            run(
                f"UNWIND $rows AS row MERGE (n:{safe_name(labels[0])} {{key: row.key}}) SET n:{lbl} SET n += row.props, n.managed = true, n.proj_gen = $gen",
                rows=rows,
                gen=self.gen,
            )
            n_nodes += len(rows)
        for (rtype, fl, tl), items in self.rels.items():
            run(
                f"UNWIND $rows AS row MATCH (a:{safe_name(fl)} {{key: row.from}}) MATCH (b:{safe_name(tl)} {{key: row.to}}) "
                f"MERGE (a)-[r:{safe_name(rtype)}]->(b) SET r += row.props, r.managed = true, r.proj_gen = $gen",
                rows=items,
                gen=self.gen,
            )
            n_rels += len(items)
        # 이번 세대에 없는 관리 대상 정리
        run("MATCH ()-[r]->() WHERE r.managed = true AND r.proj_gen < $gen DELETE r", gen=self.gen)
        run("MATCH (n) WHERE n.managed = true AND n.proj_gen < $gen DETACH DELETE n", gen=self.gen)
        return {"nodes": n_nodes, "relationships": n_rels}


def _datasets_in_args(args: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(args, dict):
        for k, v in args.items():
            if k == "dataset" and isinstance(v, str):
                out.add(v)
            else:
                out |= _datasets_in_args(v)
    elif isinstance(args, list):
        for v in args:
            out |= _datasets_in_args(v)
    return out


def ensure_constraints(labels: Iterable[str]) -> None:
    for lbl in labels:
        run(f"CREATE CONSTRAINT {safe_name(lbl).lower()}_key IF NOT EXISTS FOR (n:{safe_name(lbl)}) REQUIRE n.key IS UNIQUE")


def project_all(session: Session) -> dict[str, Any]:
    schema = active_schema(session)
    if not schema:
        raise RuntimeError("활성 온톨로지 스키마가 없습니다")
    labels = {c["label"] for c in schema.classes}
    rels = {r["type"] for r in schema.relations}
    gen = int(time.time() * 1000)
    b = Batch(schema.version, gen, labels, rels)
    ensure_constraints(labels)

    # 1) 데이터셋 · 버전 · 결정론 매핑(ONT-14)
    for ds in session.execute(select(Dataset).where(Dataset.active)).scalars():
        b.node("Dataset", ds.code, {"name": ds.name, "origin": ds.origin, "kind": ds.kind, "refresh_cycle": ds.refresh_cycle}, origin=ds.origin, src_kind="dataset", src_ref=f"cfg.dataset({ds.code})")
        v, rows = current_rows(session, ds)
        for cv in current_versions(session, ds):
            vkey = f"{ds.code}:v{cv.version}"
            b.node("DatasetVersion", vkey, {"version": cv.version, "as_of": cv.as_of.isoformat() if cv.as_of else None, "data_origin": cv.data_origin, "committed_at": cv.committed_at.isoformat() if cv.committed_at else None, "file": cv.file_name}, origin=ds.origin, src_kind="dataset", src_ref=f"{ds.origin}.dataset_version({cv.id})")
            b.rel("HAS_VERSION", "Dataset", ds.code, "DatasetVersion", vkey)
        mapping = ds.mapping or {}
        for spec in mapping.get("nodes", []):
            for r in rows:
                key = r.get(spec["key_col"])
                if key in (None, ""):
                    continue
                props = {p: r.get(c) for p, c in (spec.get("props") or {}).items()}
                b.node(spec["label"], key, {"name": r.get(spec.get("name_col", spec["key_col"])), **props}, origin=ds.origin, src_kind="dataset", src_ref=f"{ds.code} v{v.version if v else '-'}")
        for spec in mapping.get("edges", []):
            for r in rows:
                fk, tk = r.get(spec["from"]["col"]), r.get(spec["to"]["col"])
                if fk in (None, "") or tk in (None, ""):
                    continue
                b.rel(spec["type"], spec["from"]["label"], fk, spec["to"]["label"], tk, src_ref=ds.code)
        for c in mapping.get("concepts", []):
            # 고정 개념 노드 + 데이터셋과의 관계 (예: RatingModel CORP_MICRO, Segment 소기업)
            b.node(c["label"], c["key"], c.get("props") or {"name": c.get("name", c["key"])}, origin=ds.origin, src_kind="dataset", src_ref=ds.code)
            for e in c.get("edges", []):
                b.rel(e["type"], e.get("from_label", c["label"]), e.get("from", c["key"]), e["to_label"], e["to"], src_ref=ds.code)
            if c.get("about"):
                b.rel("DESCRIBES", "Dataset", ds.code, c["label"], c["key"], src_ref=ds.code)

    # 2) 지표 · 워크플로우 계보 (영향 범위 질의 원천, EVT-03)
    metrics = session.execute(select(Metric)).scalars().all()
    for m in metrics:
        b.node("Metric", m.code, {"name": m.label, "unit": m.unit, "formula": m.formula, "enabled": m.enabled}, src_kind="metric", src_ref=f"cfg.metric({m.code})")
        for dcode in _datasets_in_args(m.args):
            b.rel("FEEDS", "Dataset", dcode, "Metric", m.code)
        for ref in (m.args or {}).values():
            if isinstance(ref, dict) and "metric" in ref:
                b.rel("DERIVED_FROM", "Metric", m.code, "Metric", ref["metric"])
    for wf in session.execute(select(Workflow)).scalars():
        b.node("Workflow", wf.code, {"name": wf.name, "enabled": wf.enabled}, src_kind="workflow", src_ref=f"cfg.workflow({wf.code})")
        for m in metrics:
            if m.workflow_code == wf.code and m.enabled:
                b.rel("USES", "Workflow", wf.code, "Metric", m.code)
        for out in wf.outputs or []:
            b.node("Artifact", out, {"name": out}, src_kind="workflow")
            b.rel("PRODUCES", "Workflow", wf.code, "Artifact", out)
    for t in session.execute(select(WorkflowTrigger).where(WorkflowTrigger.enabled)).scalars():
        if t.kind in ("dataset", "master"):
            b.rel("USES", "Workflow", t.workflow_code, "Dataset", t.target)
        elif t.kind == "doc_class":
            b.node("DocClass", t.target, {"name": t.target}, src_kind="workflow")
            b.rel("READS_CLASS", "Workflow", t.workflow_code, "DocClass", t.target)

    # 3) 문서 · 발행기관 · 추출 결과(검증 통과분)
    n_docs = 0
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in session.execute(select(t.document).where(t.document.is_current)).scalars():
            n_docs += 1
            dkey = f"{origin}:{d.doc_code}"
            extra_label = "BankDocument" if origin == "bank" else "ExternalDocument"
            b.node(("Document", extra_label), dkey, {"name": d.title, "title": d.title, "doc_class": d.doc_class, "doc_id": d.id, "version": d.version, "doc_origin": origin, "published_at": d.published_at.isoformat() if d.published_at else None}, origin=origin, src_kind="document", src_ref=f"{origin}.document({d.id})")
            b.node("DocClass", d.doc_class, {"name": d.doc_class}, src_kind="document")
            b.rel("IN_CLASS", "Document", dkey, "DocClass", d.doc_class)
            if d.issuer:
                b.node("Issuer", d.issuer, {"name": d.issuer, "official": bool((d.meta or {}).get("isOfficial", True))}, origin=origin, src_kind="document")
                b.rel("ISSUED_BY", "Document", dkey, "Issuer", d.issuer)
            ex = d.extraction or {}
            by = ex.get("by", "rule")
            for e in ex.get("entities", []):
                b.node(e["label"], e["key"], {"name": e.get("name") or e["key"], **(e.get("props") or {})}, origin=origin, src_kind="document", src_ref=f"{origin}.document({d.id}) p.{e.get('page') or '-'}", extracted_by=by)
            for r in ex.get("relations", []):
                fl, fk = (r["from_label"], r["from"]) if r.get("from") != "$doc" else ("Document", dkey)
                b.rel(r["type"], fl, fk, r["to_label"], r["to"], r.get("props"), extracted_by=by, src_ref=f"{origin}.document({d.id})")
    # 4) 분석 결과(질문하기 색인) ↔ 개념 — 산출물이 언급한 개념 (KB-07). 원장은 PostgreSQL(kb_chunk.concepts), 그래프는 투영(비워도 재투영으로 복원)
    from .extraction import Resolver

    label_of = {key: label for label, amap in Resolver(schema).alias.items() for key in amap.values()}
    n_mentions = 0
    for skey, concept in session.execute(select(KbChunk.source_key, func.unnest(KbChunk.concepts).label("concept")).distinct()).all():
        label = label_of.get(concept)
        if not label:
            continue
        b.node("Artifact", skey, {"name": skey}, src_kind="artifact", src_ref=f"app.kb_chunk({skey})")
        b.rel("MENTIONS", "Artifact", skey, label, concept, src_ref=f"app.kb_chunk({skey})")
        n_mentions += 1
    stats = b.flush()
    return {**stats, "artifact_mentions": n_mentions, "documents": n_docs, "generation": gen, "schema_version": schema.version, "rejected": sorted(set(b.rejected))[:50]}


def impact_of_dataset(code: str) -> list[dict[str, Any]]:
    """데이터셋 갱신 시 영향을 받는 워크플로우 (설계 §19.3 영향 범위 질의)."""
    return run(
        "MATCH (d:Dataset {key:$code})-[:FEEDS]->(m:Metric)<-[:USES]-(w:Workflow {enabled:true}) "
        "OPTIONAL MATCH (w)-[:PRODUCES]->(o) "
        "RETURN w.key AS workflow, collect(DISTINCT m.key) AS via_metrics, collect(DISTINCT o.key) AS outputs",
        code=code,
    )


def stats() -> dict[str, Any]:
    labels = run("MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS n ORDER BY n DESC")
    rels = run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY n DESC")
    return {"labels": labels, "relationships": rels}
