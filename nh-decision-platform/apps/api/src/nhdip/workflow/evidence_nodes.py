"""문서 근거 붙이기(attach_evidence) — 화면의 근거 칸을 실행 때마다 올라온 문서로 채운다.

화면 틀(기본 업무 구성)에는 문서 인용이 없다. 의견 · 제안 · 수행방안 · 화면 근거 칸(`evidence`)과 제약 근거 문서(`basisDoc` · 제약의 `doc`)마다
그 칸의 제목 · 문장 · 수치 이름으로 하이브리드 검색(키워드 · 의미)을 하고, 근거 선별(시점 · 분류 · 범주 균형)을 거친 구간을 붙인다.
- LLM 없이 동작한다(임베딩이 없으면 키워드 검색만). 데이터 근거(계산 결과를 가리키는 항목)는 그대로 두고 문서 근거만 바꾼다.
- 문서가 없거나 맞는 구간이 없으면 문서 근거를 비운다 — 예전 문서 인용이 남지 않는다.
- 같은 id 의 의견이 여러 산출물에 실려 있으면 같은 근거를 붙인다(한 번만 검색).
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import select

from nhdip.graph.evidence import rank_evidence
from nhdip.graph.search import hybrid_search, query_terms
from nhdip.llm import LlmError, embed
from nhdip.models import WorkflowNode, source

from .engine import NodeResult, RunContext, node_impl
from .nodes import _embedder, _walk_dicts, target_figures

TEXT_FIELDS = ("title", "label", "heading", "statement", "judgement", "body", "guideline", "summary")
MARK = re.compile(r"\[\[[^\]]*\]\]")
TERM_MARK = re.compile(r"\{\{term:[^|}]+\|([^}]*)\}\}")
SENT = re.compile(r"(?<=[.!?。])\s+|\n+")


def _plain(s: Any) -> str:
    t = TERM_MARK.sub(r"\1", str(s or ""))
    t = MARK.sub(" ", t)
    t = re.sub(r"[0-9.,%+\-–()·:/~]+", " ", t)
    return " ".join(t.split())


def _query(arts: dict[str, Any], d: dict[str, Any], extra: str = "") -> str:
    """칸의 제목 · 문장 · 수치 이름 → 검색어(앞쪽 질의어가 우선 — 검색은 앞 12개 낱말을 쓴다)."""
    parts = [extra] if extra else []
    parts += [_plain(d.get(f)) for f in TEXT_FIELDS if isinstance(d.get(f), str)]
    parts += [_plain(f.get("label")) for f in list(target_figures(arts, d).values())[:8]]
    parts += [_plain(x) for x in (d.get("monitoringMetrics") or [])[:4] if isinstance(x, str)]
    seen: list[str] = []
    for w in " ".join(p for p in parts if p).split():
        if len(w) >= 2 and w not in seen:
            seen.append(w)
    return " ".join(seen[:24])


def _snippet(text: str, terms: list[str], n: int = 220) -> str:
    """근거 구간에서 질의어가 가장 많이 든 문장(원문 그대로 — 문서 뷰어가 그 글을 찾아 강조한다)."""
    sents = [s.strip() for s in SENT.split(text or "") if s and s.strip()]
    if not sents:
        return (text or "")[:n]
    best = max(sents, key=lambda s: (sum(1 for t in terms if t in s), -abs(len(s) - 120)))
    return best[:n]


def _doc_meta(ctx: RunContext, hits: list[dict[str, Any]]) -> dict[tuple[str, int], Any]:
    out: dict[tuple[str, int], Any] = {}
    for origin in {h["origin"] for h in hits}:
        tbl = source(origin).document
        ids = [h["document_id"] for h in hits if h["origin"] == origin]
        for d in ctx.session.execute(select(tbl).where(tbl.id.in_(ids))).scalars():
            out[(origin, d.id)] = d
    return out


def _item(h: dict[str, Any], doc: Any, terms: list[str]) -> dict[str, Any]:
    sec = h.get("sectionPath") or h.get("section_path")
    title = doc.title if doc is not None else h.get("title")
    page = h.get("page")
    tail = (sec.split(">")[-1].strip() if sec else "")
    label = title + (f" — {tail}" if tail else "") + (f" ({page}p)" if page else "")
    ident = hashlib.sha1(f"{h['origin']}:{h['chunk_id']}".encode()).hexdigest()[:10]
    return {
        "id": f"ev-doc-{ident}",
        "doc": {"title": title, "page": page, "issuer": getattr(doc, "issuer", None) or h.get("issuer"), "dbClass": h.get("doc_class"),
                "fileName": getattr(doc, "file_name", None), "sectionPath": sec, "docCode": h.get("docCode"),
                "effectiveDate": doc.published_at.isoformat() if doc is not None and doc.published_at else None,
                "isOfficial": bool(((getattr(doc, "meta", None) or {}).get("isOfficial")))},
        "label": label[:160],
        "snippet": _snippet(h.get("text") or "", terms),
        "category": h.get("category"),
        "relevance": round(float(h.get("priority") or 0), 3),
        "sourceKind": "doc_chunk",
        "chunkRef": {"origin": h["origin"], "chunkId": h["chunk_id"]},
    }


class _Searcher:
    def __init__(self, ctx: RunContext, cfg: dict[str, Any]):
        from nhdip.data.datasets import display_as_of

        self.ctx, self.cfg = ctx, cfg
        self.emb = _embedder(ctx)
        self.as_of = display_as_of(ctx.session)
        self.cache: dict[str, list[dict[str, Any]]] = {}
        self.notes: list[str] = []
        self.calls = 0

    def find(self, q: str, k: int) -> list[dict[str, Any]]:
        key = f"{k}|{q}"
        if key in self.cache:
            return self.cache[key]
        if not q:
            self.cache[key] = []
            return []
        qvec, model = None, None
        if self.emb is not None:
            try:
                qvec = embed(self.ctx.session, self.emb, [q], workflow_run_id=self.ctx.run.id, node_run_id=self.ctx.node_run_id)[0]
                model = self.emb.model
            except LlmError as exc:
                self.notes.append(f"임베딩 실패 → 키워드 검색만: {str(exc)[:120]}")
                self.emb = None
        self.calls += 1
        classes = self.cfg.get("doc_classes") or None
        cand = hybrid_search(self.ctx.session, q, query_vec=qvec, doc_classes=classes, k=k * 5, model=model)
        # 질의어 2개 이상이 맞거나(키워드) 의미가 가까운(벡터) 구간만 — 흔한 낱말 하나만 겹친 구간은 근거로 보지 않는다
        need = min(int(self.cfg.get("min_terms", 2)), max(1, len(query_terms(q))))
        max_dist = float(self.cfg.get("max_distance", 0.5))
        cand = [h for h in cand if float((h.get("signals") or {}).get("keyword_score") or 0) >= need or float((h.get("signals") or {}).get("cosine_distance") or 9) <= max_dist]
        ranked = rank_evidence(self.ctx.session, cand, k=k, as_of=self.as_of, doc_classes=classes, query_terms=len(query_terms(q)))
        hits = ranked["hits"]
        docs = _doc_meta(self.ctx, hits)
        terms = query_terms(q)
        out = [_item(h, docs.get((h["origin"], h["document_id"])), terms) for h in hits]
        self.cache[key] = out
        return out


def _owner_slots(payload: Any):
    """근거 칸 — (객체, 종류). 근거 목록 안(문서 · 데이터 근거 항목)으로는 내려가지 않는다."""
    stack = [payload]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if isinstance(o.get("evidence"), list):
                yield o, "evidence"
            if "basisDoc" in o:
                yield o, "basisDoc"
            elif "doc" in o and ("label" in o or "kind" in o) and not o.get("snippet"):
                yield o, "doc"  # 제약 · 한도 항목의 근거 문서(자본 화면 등)
            stack.extend(v for k, v in o.items() if k != "evidence")
        elif isinstance(o, list):
            stack.extend(o)


@node_impl("attach_evidence", "문서 근거 붙이기 — 의견 · 제안 · 수행방안 · 화면 근거 칸마다 올라온 문서에서 근거 구간을 찾아 붙인다(LLM 없이 동작, 데이터 근거는 유지)")
def n_attach_evidence(ctx: RunContext, node: WorkflowNode) -> NodeResult:
    cfg = node.config or {}
    k = int(cfg.get("k", 3))
    queries: dict[str, str] = cfg.get("queries") or {}  # 산출물 · 객체 id 별 검색어 앞머리(제목이 없는 화면 근거 칸 등)
    arts = ctx.load_artifacts()
    s = _Searcher(ctx, cfg)
    by_id: dict[str, list[dict[str, Any]]] = {}
    filled, emptied, slots = 0, 0, 0
    keys = [k_ for k_ in (ctx.workflow.outputs or []) if k_ in arts]
    for key in keys:
        payload = arts[key]
        changed = False
        for obj, kind in list(_owner_slots(payload)):
            slots += 1
            oid = obj.get("id") if isinstance(obj.get("id"), str) else None
            extra = queries.get(oid or "") or (queries.get(key, "") if obj is payload else "")
            if kind == "evidence":
                if oid and oid in by_id:
                    docs = by_id[oid]
                else:
                    docs = s.find(_query(arts, obj, extra), k)
                    if oid:
                        by_id[oid] = docs
                keep = [e for e in obj["evidence"] if not (isinstance(e, dict) and isinstance(e.get("doc"), dict))]
                new = keep + docs
                if new != obj["evidence"]:
                    obj["evidence"] = new
                    changed = True
                filled += 1 if docs else 0
                emptied += 0 if docs else 1
                # 배치 확인(정책 · 의사결정 문서와 맞춰 봤는지) — 붙은 문서 이름. 판정(aligned · conflict)은 사람이 확인하기 전까지 바꾸지 않는다
                al = obj.get("alignment")
                if isinstance(al, dict) and isinstance(al.get("matched"), list):
                    m = [f"{e['doc'].get('title')}" for e in docs if e.get("category") in ("external_policy", "internal_direction")]
                    m = list(dict.fromkeys(m))[:4]
                    if m != al["matched"]:
                        al["matched"] = m
                        changed = True
            else:
                hits = s.find(_query(arts, obj, extra), 1)
                doc = hits[0]["doc"] if hits else None
                if doc != obj.get(kind):
                    obj[kind] = doc
                    changed = True
        if changed:
            ctx.changed.add(key)
    status = "succeeded" if not s.notes else "degraded"
    return NodeResult({"slots": slots, "with_documents": filled, "without_documents": emptied, "searches": s.calls, "embedding": s.emb is not None, "notes": s.notes[:5]}, status)
