"""질의 이해 (요구사항 RAG-03 · 설계 §21.6) — 질의어 · 개념 · 개념 확장 · 후속 질문 재작성.

- 질의어: 조사를 뗀 어절(예: '증가율과' → '증가율')에서 불용어를 뺀다.
- 개념: 온톨로지 별칭 사전 부분 일치(포용금융 · 소기업 · 햇살론 …).
- 개념 확장: 개념에서 무방향 1홉 이웃. 간선 원천은 데이터셋 매핑(PostgreSQL — 항상 가능), Neo4j 는 추가 간선(장애 시 건너뜀).
- 후속 질문: '그럼 소기업은?' 같은 질문을 직전 대화의 개념 · 핵심어로 독립형 질문으로 다시 쓴다(규칙 + 선택적 LLM).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.graph.extraction import Resolver
from nhdip.graph.neo4j_client import GraphUnavailable, run
from nhdip.graph.projection import active_schema
from nhdip.llm import LlmError, LlmUnavailable, chat, parse_json, resolve
from nhdip.llm.guard import GUARD, fence
from nhdip.models import Dataset

from .access import setting_dict
from .defaults import REWRITE_DEFAULT

log = logging.getLogger("nhdip.knowledge")

TERM = re.compile(r"[0-9A-Za-z가-힣]{2,}")
PARTICLES = ("으로", "에서", "까지", "부터", "과", "와", "은", "는", "이", "가", "을", "를", "의", "에", "로", "도", "만")
STOP = {"얼마", "어떻게", "무엇", "알려줘", "알려", "주세요", "현재", "최근", "대비", "관련", "있나요", "인가요", "어때"}
FOLLOW_PREFIX = ("그럼", "그러면", "그렇다면", "그리고", "또한", "그건", "이건", "그것", "이것", "거기", "그중", "그 중", "반면", "한편", "그 외", "그외")
PRONOUNS = ("그것", "이것", "그건", "이건", "그거", "이거", "거기", "해당", "앞서", "방금", "위의", "위 ", "그 부분", "같은 기준")
CONCEPT_LABELS = ["PolicyTheme", "ProductGroup", "Segment", "RatingModel", "BusinessDomain", "CapitalConstraint"]


def terms_of(q: str) -> list[str]:
    """질문 어절 + 조사를 뗀 형태 (예: '증가율과' → '증가율', '이탈은' → '이탈')."""
    out: list[str] = []
    for t in TERM.findall(q or ""):
        for cand in (t, *(t[: -len(p)] for p in PARTICLES if t.endswith(p) and len(t) - len(p) >= 2)):
            if cand not in STOP and cand not in out:
                out.append(cand)
    return out


def query_tokens(q: str) -> list[str]:
    """질문의 의미 있는 낱말 수 계산용 — 어절마다 조사를 뗀 형태 하나만(원형 · 조사형을 따로 세지 않는다)."""
    out: list[str] = []
    for t in TERM.findall(q or ""):
        stem = next((t[: -len(p)] for p in PARTICLES if t.endswith(p) and len(t) - len(p) >= 2), t)
        if t in STOP or stem in STOP:
            continue
        if stem not in out:
            out.append(stem)
    return out


def concept_aliases(session: Session, concepts: list[str]) -> list[str]:
    """질문 개념 키들의 별칭(소문자, 2자 이상) — 문서 본문에 개념이 직접 나오는지 볼 때 쓴다."""
    schema = active_schema(session)
    if schema is None or not concepts:
        return []
    want = set(concepts)
    return sorted({alias for amap in Resolver(schema).alias.values() for alias, key in amap.items() if key in want and len(alias) >= 2})


def concepts_of(session: Session, q: str) -> list[str]:
    """질문에 나온 온톨로지 개념 키(별칭 사전 부분 일치)."""
    schema = active_schema(session)
    if not schema:
        return []
    low = (q or "").lower()
    found: list[str] = []
    for amap in Resolver(schema).alias.values():
        for alias, key in amap.items():
            if len(alias) >= 2 and alias in low and key not in found:
                found.append(key)
    return found


# ── Neo4j 차단기 — 연결이 막히면 일정 시간 건너뛰어 질문마다 대기하지 않는다 ──────────
_DOWN_UNTIL = 0.0
_FAILS = 0
BREAKER_SEC = 30.0
BREAKER_MAX_SEC = 300.0


def graph_up() -> bool:
    return time.monotonic() >= _DOWN_UNTIL


def mark_graph_down() -> None:
    """연속 실패마다 건너뛰는 시간을 두 배로(30초 → 60 → 120 → … 최대 5분) — 막힌 연결을 시도하느라 질문이 기다리는 일을 줄인다."""
    global _DOWN_UNTIL, _FAILS
    _DOWN_UNTIL = time.monotonic() + min(BREAKER_MAX_SEC, BREAKER_SEC * (2 ** _FAILS))
    _FAILS += 1


def mark_graph_ok() -> None:
    global _FAILS
    _FAILS = 0


def reset_graph_breaker() -> None:
    global _DOWN_UNTIL, _FAILS
    _DOWN_UNTIL = 0.0
    _FAILS = 0


# ── 개념 확장 ────────────────────────────────────────────────
def concept_edges(session: Session) -> dict[str, list[tuple[str, str]]]:
    """개념 간선 인접 목록 {키: [(이웃, 관계)]} — 데이터셋 매핑의 개념 간선(PostgreSQL 원천). 무방향."""
    from nhdip.data.sources import Resolver

    adj: dict[str, list[tuple[str, str]]] = {}
    mappings = list(session.execute(select(Dataset.mapping).where(Dataset.active)).scalars())
    # 업무 구성 '자료'의 온톨로지 연결 — 그 자료가 이어졌을 때(Phase O · BIZ-03, 그래프 투영과 같은 기준)
    res = Resolver(session)
    mappings += [sp.mapping for sp in res.specs.values() if sp.mapping and res.resolve(sp.name) is not None]
    for mapping in mappings:
        for c in (mapping or {}).get("concepts") or []:
            key = c.get("key")
            for e in c.get("edges") or []:
                to, typ = e.get("to"), e.get("type") or "RELATED"
                if key and to:
                    adj.setdefault(str(key), []).append((str(to), typ))
                    adj.setdefault(str(to), []).append((str(key), typ))
    return adj


def _graph_neighbors(keys: list[str]) -> list[tuple[str, str, str]]:
    if not keys or not graph_up():
        return []
    try:
        rows = run(
            "MATCH (c)-[r]-(n) WHERE c.key IN $keys AND any(l IN labels(c) WHERE l IN $labels) AND any(l IN labels(n) WHERE l IN $labels) "
            "RETURN DISTINCT c.key AS src, n.key AS key, type(r) AS rel LIMIT 80",
            keys=keys, labels=CONCEPT_LABELS,
        )
    except GraphUnavailable:
        mark_graph_down()
        return []
    mark_graph_ok()
    return [(r["src"], r["key"], r["rel"]) for r in rows if r.get("key")]


def expand_concepts(session: Session, concepts: list[str], max_n: int = 24, *, use_graph: bool = True) -> list[dict[str, Any]]:
    """개념의 1홉 이웃 — [{key, from, via, source}] (이미 질문에 있는 개념은 뺀다)."""
    have = set(concepts)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(src: str, key: str, via: str, source: str) -> None:
        if key not in have and key not in seen and len(out) < max_n:
            seen.add(key)
            out.append({"key": key, "from": src, "via": via, "source": source})

    adj = concept_edges(session)
    for c in concepts:
        for nb, rel in adj.get(c, []):
            add(c, nb, rel, "ontology")
    if use_graph:
        for src, nb, rel in _graph_neighbors(concepts):
            add(src, nb, rel, "graph")
    return out


# ── 후속 질문 재작성 ──────────────────────────────────────────
@dataclass
class Rewrite:
    query: str
    used: bool = False
    by: str | None = None  # rule | llm


def clean_history(history: Any, limit: int = 3) -> list[dict[str, str]]:
    """클라이언트가 보낸 이력 정리 — 최근 limit 개, 문자열만, 길이 상한."""
    out: list[dict[str, str]] = []
    for h in history or []:
        if isinstance(h, dict) and isinstance(h.get("q"), str) and h["q"].strip():
            out.append({"q": h["q"].strip()[:300], "a": str(h.get("a") or "")[:400]})
    return out[-limit:]


def is_followup(question: str, history: list[dict[str, str]], concepts: list[str]) -> bool:
    if not history:
        return False
    q = question.strip()
    if q.startswith(FOLLOW_PREFIX) or any(p in q for p in PRONOUNS):
        return True
    return len(terms_of(q)) <= 3 and not concepts


def rule_rewrite(session: Session, question: str, history: list[dict[str, str]]) -> str:
    """직전 대화의 개념 · 핵심어를 앞에 붙인다 — 가장 최근에 '주제(개념)'가 있던 질문을 고른다(없으면 직전 질문)."""
    prev = next((h["q"] for h in reversed(history) if concepts_of(session, h["q"])), history[-1]["q"])
    carry = [c for c in concepts_of(session, prev) if c not in question]
    carry += [t for t in terms_of(prev)[:6] if t not in question and t not in carry]
    return " ".join([*carry[:6], question]).strip()


def _digits(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s or ""))


def agent_llm(session: Session, code: str, fallback: str = "query_assistant") -> tuple[Any, bool]:
    """(설정, 자기 에이전트인지) — Phase M · LLM-P07. 전용 에이전트(query_rewriter · search_reranker)가 있으면 그 연결 · 모델 · 프롬프트 판,
    에이전트가 없거나(이전 DB) 연결이 안 되면 이전처럼 AI 어시스턴트 연결. 관리자가 전용 에이전트를 끄면 LLM 을 쓰지 않는다(LlmUnavailable)."""
    from nhdip.models import Agent

    a = session.get(Agent, code)
    if a is not None and not a.enabled:
        raise LlmUnavailable(f"에이전트 비활성: {code}")
    if a is not None:
        try:
            return resolve(session, code), True
        except LlmUnavailable:
            pass
    return resolve(session, fallback), False


REWRITE_TASK = "대화 맥락을 반영해 마지막 질문을 독립적으로 이해되는 한국어 질문 한 문장으로 다시 쓴다. 새로운 사실 · 숫자를 만들지 않는다. JSON 하나: {\"query\": \"...\"}"


def llm_rewrite(session: Session, question: str, history: list[dict[str, str]]) -> str | None:
    try:
        cfg, own = agent_llm(session, "query_rewriter")
        convo = "\n".join(f"Q: {h['q']}\nA: {h['a'][:200]}" for h in history)
        system = (cfg.system_prompt if own and cfg.system_prompt else "너는 검색 질의 재작성기다.") + "\n\n" + GUARD
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"과제: {REWRITE_TASK}\n\n이전 대화:\n{fence(convo)}\n\n마지막 질문:\n{fence(question)}"},
        ]
        res = chat(session, cfg, messages, json_mode=True, purpose="assist_rewrite")
        q = str(parse_json(res.text).get("query", "")).strip()
    except (LlmUnavailable, LlmError, ValueError, AttributeError):
        return None
    # 검증 — 길이 · 새 숫자 금지(이력 · 질문에 있던 숫자만)
    if not q or len(q) > 200 or not _digits(q) <= (_digits(question) | _digits(convo)):
        return None
    return q


def contextualize(session: Session, question: str, history: Any, concepts: list[str] | None = None) -> Rewrite:
    """후속 질문이면 독립형 질문으로 다시 쓴다. 아니면 원문 그대로."""
    cfg = setting_dict(session, "assist.rewrite", REWRITE_DEFAULT)
    hist = clean_history(history, int(cfg.get("max_history", 3)))
    concepts = concepts if concepts is not None else concepts_of(session, question)
    if not cfg.get("enabled", True) or not is_followup(question, hist, concepts):
        return Rewrite(question)
    if cfg.get("llm", True):
        q = llm_rewrite(session, question, hist)
        if q:
            return Rewrite(q, True, "llm")
    return Rewrite(rule_rewrite(session, question, hist), True, "rule")
