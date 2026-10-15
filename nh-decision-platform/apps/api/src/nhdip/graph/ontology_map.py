"""온톨로지 구성 지도 (Phase G · 요구사항 §23 OV-01~06 · 설계 §23.3).

원장 수집(projection.collect_graph — Neo4j 투영과 같은 코드) → 끝점 확인 → 상한 → 군집(Louvain) → 3D/2D 배치 → 요약.
모두 결정적이다(노드 순서 고정 · 고정 시드) — 같은 원장이면 같은 지도. 결과는 원장 서명이 같으면 잠시 보관한다.
"""
from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

DEFAULT_LIMIT = 1500
MAX_LIMIT = 4000
SMALL_CLUSTER = 3  # 이보다 작은 군집은 '작은 묶음' 하나로
CACHE_SEC = 300
META_KEYS = {"name", "origin", "src_kind", "src_ref", "extracted_by", "schema_version"}
# 클래스 업무 이름(화면 표기 · 군집 이름) — 스키마 라벨은 영문 식별자라 보조로만 (Q125)
from .schema import CLASS_KO  # noqa: E402 — 기본 업무 이름(스키마 ko 가 없을 때)


# ── 군집: Louvain (모듈성) ───────────────────────────────────
def _one_level(adj: list[dict[int, float]]) -> tuple[list[int], bool]:
    n = len(adj)
    k = [sum(nb.values()) for nb in adj]
    m2 = sum(k)
    comm = list(range(n))
    if m2 <= 0:
        return comm, False
    tot = k[:]
    improved = False
    for _ in range(30):
        moved = False
        for i in range(n):
            ci = comm[i]
            wc: dict[int, float] = defaultdict(float)
            for j, w in adj[i].items():
                if j != i:
                    wc[comm[j]] += w
            tot[ci] -= k[i]
            best, best_gain = ci, wc.get(ci, 0.0) - tot[ci] * k[i] / m2
            for c in sorted(wc):
                gain = wc[c] - tot[c] * k[i] / m2
                if gain > best_gain + 1e-12:
                    best, best_gain = c, gain
            tot[best] += k[i]
            if best != ci:
                comm[i] = best
                moved = improved = True
        if not moved:
            break
    return comm, improved


def louvain(n: int, edges: list[tuple[int, int]], max_levels: int = 10) -> list[int]:
    """무방향 · 가중치 없는 그래프의 군집 번호(0부터, 큰 군집 먼저). 노드 순서와 간선만으로 정해진다(난수 없음)."""
    adj: list[dict[int, float]] = [defaultdict(float) for _ in range(n)]
    for a, b in edges:
        if a != b:
            adj[a][b] += 1.0
            adj[b][a] += 1.0
    member = list(range(n))
    cur = adj
    for _ in range(max_levels):
        comm, improved = _one_level(cur)
        if not improved:
            break
        ids: dict[int, int] = {}
        comm = [ids.setdefault(c, len(ids)) for c in comm]
        member = [comm[m] for m in member]
        nxt: list[dict[int, float]] = [defaultdict(float) for _ in range(len(ids))]
        for i, nb in enumerate(cur):
            for j, w in nb.items():
                nxt[comm[i]][comm[j]] += w
        cur = nxt
    sizes = Counter(member)
    order = {c: r for r, (c, _) in enumerate(sorted(sizes.items(), key=lambda x: (-x[1], x[0])))}
    return [order[m] for m in member]


# ── 배치: 힘 배치(Fruchterman–Reingold) ──────────────────────
def force_layout(n: int, edges: list[tuple[int, int, float]], dim: int, iters: int, seed: int = 7) -> np.ndarray:
    """[-1, 1] 안의 좌표(n × dim). 고정 시드 · 고정 반복 수라 결정적."""
    if n == 0:
        return np.zeros((0, dim))
    if n == 1:
        return np.zeros((1, dim))
    rng = np.random.default_rng(seed)
    pos = rng.uniform(-1.0, 1.0, size=(n, dim))
    k = 1.0 / math.sqrt(n) * (1.6 if dim == 3 else 1.2)
    if edges:
        ea = np.array([e[0] for e in edges])
        eb = np.array([e[1] for e in edges])
        ew = np.array([e[2] for e in edges], dtype=float)
    iters = max(10, iters)
    for it in range(iters):
        t = 0.12 * (1.0 - it / iters) + 0.004
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta ** 2).sum(-1)) + 1e-6
        rep = (k * k / dist ** 2)[:, :, None] * delta
        disp = rep.sum(1)
        if edges:
            d = pos[ea] - pos[eb]
            dl = np.sqrt((d ** 2).sum(-1)) + 1e-6
            f = (dl / k * ew)[:, None] * d
            np.add.at(disp, ea, -f)
            np.add.at(disp, eb, f)
        # 중심으로 약하게 당겨 흩어지지 않게
        disp -= pos * 0.05
        ln = np.sqrt((disp ** 2).sum(-1)) + 1e-9
        pos += disp / ln[:, None] * np.minimum(ln, t)[:, None]
    pos -= pos.mean(0)
    span = np.abs(pos).max() or 1.0
    return pos / span


def _iters(n: int) -> int:
    # 큰 묶음은 반복을 줄여 계산 시간을 일정하게(n² 연산)
    return int(min(160, max(25, 60000 / max(1, n))))


FLAT_Y = 0.62  # 화면은 가로가 넓다 — 군집 중심을 위아래로 덜 퍼지게(납작한 구 · 타원)


def _shell_points(k: int, dim: int) -> np.ndarray:
    """k 개의 고르게 퍼진 방향 — 3D 는 피보나치 구, 2D 는 원(둘 다 세로를 눌러 화면 비율에 맞춤)."""
    if dim == 2:
        a = np.arange(k) * (2 * math.pi / max(1, k)) - math.pi / 2
        return np.stack([np.cos(a), np.sin(a) * FLAT_Y], 1)
    i = np.arange(k) + 0.5
    phi = np.arccos(1 - 2 * i / k)
    theta = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.cos(phi) * FLAT_Y, np.sin(theta) * np.sin(phi)], 1)


def _cluster_centers(sizes: list[int], between: dict[tuple[int, int], int], radii: np.ndarray, dim: int) -> np.ndarray:
    """군집 중심 — 구(원) 위에 고르게 놓되, 서로 많이 엮인 군집을 이웃 자리에(탐욕 배정), 이어서 겹치지 않게 벌리고 엮인 군집끼리 살짝 당긴다."""
    k = len(sizes)
    if k == 1:
        return np.zeros((1, dim))
    shell = _shell_points(k, dim)
    base = max(1.0, float(radii.sum()) / (math.pi if dim == 2 else 2.2))
    w = np.zeros((k, k))
    for (a, b), v in between.items():
        w[a, b] = w[b, a] = math.log1p(v)
    order = [int(np.argmax(sizes))]
    while len(order) < k:
        rest = [c for c in range(k) if c not in order]
        order.append(max(rest, key=lambda c: (w[c, order].sum(), sizes[c], -c)))
    # 자리 배정 — 앞 군집과 가장 많이 엮인 군집이 그 군집에서 가까운 빈 자리로
    pos = np.zeros((k, dim))
    free = list(range(k))
    for idx, c in enumerate(order):
        if idx == 0:
            slot = free[0]
        else:
            tw = float(w[c, order[:idx]].sum())
            anchor = sum(w[c, p] * pos[p] for p in order[:idx]) / tw if tw > 0 else pos[order[0]]
            slot = min(free, key=lambda s: (float(np.linalg.norm(shell[s] * base - anchor)), s))
        free.remove(slot)
        pos[c] = shell[slot] * base
    for _ in range(80):
        disp = np.zeros_like(pos)
        for a in range(k):
            for b in range(a + 1, k):
                d = pos[a] - pos[b]
                dist = float(np.linalg.norm(d)) + 1e-9
                need = radii[a] + radii[b] + 0.12
                if dist < need:  # 겹침 — 밀어냄
                    push = d / dist * (need - dist) / 2
                    disp[a] += push
                    disp[b] -= push
                elif w[a, b] > 0:  # 엮인 군집 — 살짝 당김
                    pull = d / dist * min(0.02 * w[a, b], (dist - need) / 4)
                    disp[a] -= pull
                    disp[b] += pull
        pos += disp
        norms = np.linalg.norm(pos, axis=1, keepdims=True) + 1e-9
        pos = pos / norms * np.clip(norms, 0.55 * base, 1.25 * base)  # 혼자 떨어진 군집이 너무 멀리 가지 않게
    return pos


def _fit_unit(sub: np.ndarray) -> np.ndarray:
    """군집 안 배치를 반지름 1 안으로 — 멀리 튀어나간 한두 점 때문에 나머지가 작아지지 않게 95% 거리 기준."""
    if len(sub) <= 2:
        return sub
    nrm = np.linalg.norm(sub, axis=1)
    scale = float(np.percentile(nrm, 95)) or 1.0
    out = sub / scale
    over = np.linalg.norm(out, axis=1, keepdims=True)
    return np.where(over > 1.15, out / over * 1.15, out)


def layout(n: int, cluster: list[int], links: list[tuple[int, int]], dim: int) -> tuple[np.ndarray, dict[int, list[float]]]:
    """군집 중심 배치 → 군집 안 배치 → 합침. 반환: (좌표 n × dim, 군집 중심)."""
    if n == 0:
        return np.zeros((0, dim)), {}  # 개체가 없는 지도(올린 자료가 없을 때 — M.23)
    groups: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(cluster):
        groups[c].append(i)
    cids = sorted(groups)
    cidx = {c: i for i, c in enumerate(cids)}
    between: Counter[tuple[int, int]] = Counter()
    for a, b in links:
        ca, cb = cluster[a], cluster[b]
        if ca != cb:
            between[(min(cidx[ca], cidx[cb]), max(cidx[ca], cidx[cb]))] += 1
    sizes = [len(groups[c]) for c in cids]
    biggest = max(sizes)
    radii = np.array([0.16 + 0.34 * math.sqrt(s / biggest) for s in sizes])
    centers = _cluster_centers(sizes, dict(between), radii, dim)
    pos = np.zeros((n, dim))
    centers_out: dict[int, list[float]] = {}
    for c in cids:
        members = groups[c]
        loc = {g: i for i, g in enumerate(members)}
        inner = [(loc[a], loc[b], 1.0) for a, b in links if a in loc and b in loc and a != b]
        sub = _fit_unit(force_layout(len(members), inner, dim, _iters(len(members)), seed=13 + c))
        ctr = centers[cidx[c]]
        pos[members] = ctr + sub * radii[cidx[c]]
        centers_out[c] = [round(float(x), 4) for x in ctr]
    span = np.abs(pos).max() or 1.0
    pos /= span
    centers_out = {c: [round(float(x) / span, 4) for x in v] for c, v in centers_out.items()}
    return pos, centers_out


# ── 지도 만들기 ──────────────────────────────────────────────
def _short(v: Any) -> Any:
    if isinstance(v, str):
        return v[:80]
    if isinstance(v, list):
        return [_short(x) for x in v[:6]]
    return v


def select_nodes(ids: list[str], cls_of: dict[str, str], deg: dict[str, int], limit: int) -> list[str]:
    """상한 안에서 남길 노드 — 클래스마다 최소 몫(연결 수 높은 순) 뒤 전체 연결 수 순 (OV-06)."""
    if len(ids) <= limit:
        return ids
    by_cls: dict[str, list[str]] = defaultdict(list)
    for i in ids:
        by_cls[cls_of[i]].append(i)
    keep: list[str] = []
    seen: set[str] = set()
    for c in sorted(by_cls):
        members = sorted(by_cls[c], key=lambda x: (-deg.get(x, 0), x))
        quota = max(5, int(limit * len(members) / len(ids) * 0.3))
        for x in members[:quota]:
            keep.append(x)
            seen.add(x)
    for x in sorted(ids, key=lambda x: (-deg.get(x, 0), x)):
        if len(keep) >= limit:
            break
        if x not in seen:
            keep.append(x)
            seen.add(x)
    return keep[:limit]


def build_map(batch: Any, schema: Any, *, limit: int = DEFAULT_LIMIT, classes: list[str] | None = None) -> dict[str, Any]:
    """collect_graph 결과(Batch) → 지도 응답(설계 §23.4)."""
    limit = max(10, min(MAX_LIMIT, int(limit)))
    want = set(classes or [])
    node_info: dict[str, dict[str, Any]] = {}
    for labels, items in batch.nodes.items():
        cls = labels[0]
        if want and cls not in want:
            continue
        for key, props in items.items():
            nid = f"{cls}:{key}"
            node_info[nid] = {"cls": cls, "key": key, "props": props}
    rel_rows: list[tuple[str, str, str]] = []
    seen_rel: set[tuple[str, str, str]] = set()
    for (rtype, fl, tl), items in batch.rels.items():
        for it in items:
            a, b = f"{fl}:{it['from']}", f"{tl}:{it['to']}"
            if a in node_info and b in node_info and a != b and (a, rtype, b) not in seen_rel:  # 끝점이 없는 관계는 Neo4j 에서도 생기지 않는다
                seen_rel.add((a, rtype, b))
                rel_rows.append((a, rtype, b))
    deg: Counter[str] = Counter()
    for a, _, b in rel_rows:
        deg[a] += 1
        deg[b] += 1
    all_ids = sorted(node_info, key=lambda x: (node_info[x]["cls"], str(node_info[x]["key"])))
    keep = select_nodes(all_ids, {i: node_info[i]["cls"] for i in all_ids}, deg, limit)
    keep_sorted = sorted(keep, key=lambda x: (node_info[x]["cls"], str(node_info[x]["key"])))
    idx = {nid: i for i, nid in enumerate(keep_sorted)}
    rel_types = sorted({r for _, r, _ in rel_rows})
    rti = {r: i for i, r in enumerate(rel_types)}
    links = [(idx[a], idx[b], rti[r]) for a, r, b in rel_rows if a in idx and b in idx]
    pairs = [(a, b) for a, b, _ in links]
    n = len(keep_sorted)
    raw_cluster = louvain(n, pairs)
    sizes = Counter(raw_cluster)
    small = {c for c, s in sizes.items() if s < SMALL_CLUSTER}
    big = sorted({c for c in sizes if c not in small}, key=lambda c: (-sizes[c], c))
    remap = {c: i for i, c in enumerate(big)}
    small_id = len(big)
    cluster = [remap.get(c, small_id) for c in raw_cluster]
    p3, c3 = layout(n, cluster, pairs, 3)
    p2, c2 = layout(n, cluster, pairs, 2)
    ldeg = Counter()
    for a, b in pairs:
        ldeg[a] += 1
        ldeg[b] += 1

    def name_of(i: int) -> str:
        info = node_info[keep_sorted[i]]
        title = (batch.meta.get((info["cls"], str(info["key"]))) or {}).get("title")
        return str(title or info["props"].get("name") or info["key"])[:80]

    nodes_out = []
    for i, nid in enumerate(keep_sorted):
        info = node_info[nid]
        p = info["props"]
        extra = {k: _short(v) for k, v in p.items() if k not in META_KEYS and v not in (None, "", [])}
        meta = batch.meta.get((info["cls"], str(info["key"]))) or {}
        node = {
            "id": nid, "cls": info["cls"], "key": str(info["key"])[:120], "name": name_of(i), "deg": int(ldeg[i]), "c": int(cluster[i]),
            "p3": [round(float(x), 4) for x in p3[i]], "p2": [round(float(x), 4) for x in p2[i]],
            "src": str(p.get("src_ref") or "")[:120], "kind": p.get("src_kind"), "by": p.get("extracted_by"), "origin": p.get("origin"),
            "props": dict(list(extra.items())[:8]),
        }
        if meta.get("evidence"):
            node["evidence"] = meta["evidence"]
            node["evidencePage"] = meta.get("page")
            node["evidenceDoc"] = meta.get("document")
        nodes_out.append(node)
    # 군집 요약
    cl_members: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(cluster):
        cl_members[c].append(i)
    desc = {c.get("label"): c.get("description", "") for c in (schema.classes or [])}
    # 업무 이름 = 스키마의 ko(Phase M · ONB-01), 없으면 이전 기본 이름
    ko_of = {c.get("label"): c.get("ko") or CLASS_KO.get(c.get("label"), c.get("label")) for c in (schema.classes or [])}
    clusters_out = []
    for c in sorted(cl_members):
        mem = cl_members[c]
        comp = Counter(node_info[keep_sorted[i]]["cls"] for i in mem)
        main = comp.most_common(1)[0][0]
        tops = [name_of(i) for i in sorted(mem, key=lambda i: (-ldeg[i], keep_sorted[i]))[:2]]
        label = "작은 묶음(연결이 적은 개체)" if c == small_id and small else " · ".join([ko_of.get(main) or CLASS_KO.get(main, main), *tops])
        clusters_out.append({"id": c, "label": label[:120], "size": len(mem), "classes": dict(comp.most_common()), "main": main, "center3": c3.get(c), "center2": c2.get(c), "small": c == small_id and bool(small)})
    cls_count = Counter(node_info[x]["cls"] for x in keep_sorted)
    all_cls_count = Counter(node_info[x]["cls"] for x in all_ids)
    class_order = [c.get("label") for c in (schema.classes or []) if c.get("label")]
    for c in sorted(all_cls_count):
        if c not in class_order:
            class_order.append(c)
    classes_out = [{"label": c, "ko": ko_of.get(c) or CLASS_KO.get(c, c), "count": int(cls_count.get(c, 0)), "total": int(all_cls_count.get(c, 0)), "description": desc.get(c, ""), "color": i} for i, c in enumerate(class_order)]
    rel_count = Counter(r for _, r, _ in rel_rows)
    triples = Counter((node_info[a]["cls"], r, node_info[b]["cls"]) for a, r, b in rel_rows)
    return {
        "classes": classes_out,
        "relTypes": rel_types,
        "relations": [{"type": r, "count": int(rel_count[r])} for r in rel_types],
        "schema": [{"from": f, "type": r, "to": t, "count": int(n_)} for (f, r, t), n_ in sorted(triples.items(), key=lambda x: (-x[1], x[0]))],
        "clusters": clusters_out,
        "nodes": nodes_out,
        "links": [list(x) for x in links],
        "truncated": len(keep_sorted) < len(all_ids),
        "total": {"nodes": len(all_ids), "links": len(rel_rows)},
        "schemaVersion": getattr(schema, "version", None),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── 보관 ─────────────────────────────────────────────────────
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def signature(session: Session) -> tuple[Any, ...]:
    """원장 서명 — 지도에 들어가는 것들의 개수 · 최근 시각. 같으면 같은 지도(보관본을 쓴다)."""
    from nhdip.models import Dataset, KbChunk, Metric, OntologySchema, Workflow, WorkflowTrigger, source

    parts: list[Any] = [
        session.scalar(select(func.max(OntologySchema.version)).where(OntologySchema.active)),
        session.scalar(select(func.count()).select_from(Dataset)),
        session.scalar(select(func.count()).select_from(Metric)),
        session.scalar(select(func.count()).select_from(Metric).where(Metric.enabled)),  # 지표를 끄면(정의 삭제 포함) 지도에서 빠진다 (M.23)
        session.scalar(select(func.count()).select_from(Workflow)),
        session.scalar(select(func.count()).select_from(Workflow).where(Workflow.enabled)),
        session.scalar(select(func.count()).select_from(WorkflowTrigger)),
        session.scalar(select(func.max(KbChunk.indexed_at))),
    ]
    for origin in ("bank", "ext"):
        t = source(origin)
        parts.append(session.scalar(select(func.max(t.version.id)).where(t.version.is_current)))
        parts.append(session.scalar(select(func.count()).select_from(t.version).where(t.version.is_current)))
        parts.append(session.scalar(select(func.max(t.document.id)).where(t.document.is_current)))
        parts.append(session.scalar(select(func.count()).select_from(t.document).where(t.document.is_current)))
    return tuple(str(p) for p in parts)


def ontology_map(session: Session, *, limit: int = DEFAULT_LIMIT, classes: list[str] | None = None, refresh: bool = False) -> dict[str, Any]:
    from .projection import active_schema, collect_graph

    key = (signature(session), int(limit), tuple(sorted(classes or [])))
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and not refresh and now - hit[0] < CACHE_SEC:
            return {**hit[1], "cached": True}
    schema = active_schema(session)
    if schema is None:
        return {"classes": [], "relTypes": [], "relations": [], "schema": [], "clusters": [], "nodes": [], "links": [], "truncated": False, "total": {"nodes": 0, "links": 0}, "empty": "활성 온톨로지 스키마가 없습니다"}
    t0 = time.perf_counter()
    out = build_map(collect_graph(session, schema), schema, limit=limit, classes=classes)
    out["elapsedMs"] = round((time.perf_counter() - t0) * 1000)
    with _cache_lock:
        for k in [k for k, (ts, _) in _cache.items() if now - ts >= CACHE_SEC]:
            _cache.pop(k, None)
        _cache[key] = (now, out)
    return {**out, "cached": False}
