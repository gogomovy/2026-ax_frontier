"""자연어 질의 (UX-06 · CALC-10) — 검색 순서는 설계 §19.2 와 같다.

1) 개념 해석: 온톨로지 별칭 사전으로 질문의 개념(포용금융 · 소기업 · 햇살론 …)을 찾는다.
2) 구조 질의: 질문과 맞는 지표의 최근 확정 값(커널 계산 · calc_run)을 가져온다 — 사용자 화면 권한 범위 안에서만.
3) 근거 검색: 개념과 연결된 문서로 좁힌 뒤(그래프) pgvector + 키워드 RRF.
4) 서술: LLM(query_assistant)은 위 값과 근거만 인용하고, 추가 계산은 calc_* 도구로만 한다.
5) 검증: 답변의 숫자가 제공 값·도구 결과·근거 원문에 있는지 확인(numeric_provenance).
LLM 을 쓸 수 없으면 수치와 근거만 결정론적으로 정리해 돌려준다.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.db import get_session
from nhdip.events import audit
from nhdip.graph.extraction import Resolver
from nhdip.graph.projection import active_schema
from nhdip.graph.evidence import rank_evidence
from nhdip.graph.search import TERM, graph_documents, hybrid_search, query_terms
from nhdip.llm import LlmError, LlmUnavailable, resolve
from nhdip.llm.guard import GUARD, fence
from nhdip.llm.tools import chat_with_tools
from nhdip.models import AppUser, Metric, MetricValue, Setting

from .deps import client_ip, require_resource, user_resources

router = APIRouter(tags=["assist"])

UNIT = {"PCT": "%", "PP": "%p", "KRW_TN": "조원", "KRW_BN": "억원", "KRW_MN": "백만원", "CNT": "건", "RATIO": ""}
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
DEFAULT_WF_RESOURCES = {"wf_model_monitoring": "risk_dashboard", "wf_inclusive_risk": "risk_dashboard", "wf_hq_goal_review": "hq_dashboard"}
STOP = {"얼마", "어떻게", "무엇", "알려줘", "알려", "주세요", "현재", "최근", "대비", "관련", "있나요", "인가요", "어때"}


class AskIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    screen: str | None = None


PARTICLES = ("으로", "에서", "까지", "부터", "과", "와", "은", "는", "이", "가", "을", "를", "의", "에", "로", "도", "만")


def _terms(q: str) -> list[str]:
    """질문 어절 + 조사를 뗀 형태 (예: '증가율과' → '증가율', '이탈은' → '이탈')."""
    out: list[str] = []
    for t in TERM.findall(q):
        for cand in (t, *(t[: -len(p)] for p in PARTICLES if t.endswith(p) and len(t) - len(p) >= 2)):
            if cand not in STOP and cand not in out:
                out.append(cand)
    return out


def _fmt(v: Decimal | None, decimals: int | None) -> str | None:
    if v is None:
        return None
    d = decimals or 0
    return f"{Decimal(v):,.{d}f}"


def concepts_of(session: Session, q: str) -> list[str]:
    schema = active_schema(session)
    if not schema:
        return []
    low = q.lower()
    found: list[str] = []
    for amap in Resolver(schema).alias.values():
        for alias, key in amap.items():
            if len(alias) >= 2 and alias in low and key not in found:
                found.append(key)
    return found


def metrics_for(session: Session, user: AppUser, q: str, concepts: list[str], limit: int = 8) -> list[dict[str, Any]]:
    allowed = user_resources(session, user)
    s = session.get(Setting, "assist.workflow_resources")
    wf_res: dict[str, str] = s.value if s else DEFAULT_WF_RESOURCES
    terms = list(dict.fromkeys(_terms(q) + concepts))  # 개념과 질문어가 같으면 한 번만
    scored = []
    for m in session.execute(select(Metric).where(Metric.enabled)).scalars():
        if allowed is not None and wf_res.get(m.workflow_code) not in allowed:
            continue
        label = m.label
        # 질문어가 지표명에 많이·길게 맞을수록 높게, 질문어 대부분이 맞는 지표를 우선
        hits = [t for t in terms if t in label]
        # 지표명 중 질문어로 덮인 비율 — 짧고 정확히 맞는 지표(예: '목표 대비 이탈')가 긴 파생 지표보다 앞선다
        covered = set()
        for t in hits:
            start = label.find(t)
            while start >= 0:
                covered.update(range(start, start + len(t)))
                start = label.find(t, start + 1)
        body = sum(1 for ch in label if not ch.isspace())
        coverage = len([i for i in covered if not label[i].isspace()]) / body if body else 0
        score = sum(len(t) for t in hits) + 2 * len(hits) + sum(0.5 for t in terms if t in m.code) + 8 * coverage
        if score:
            scored.append((score, -m.sort, m))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    out = []
    for _, _, m in scored[:limit]:
        mv = session.execute(select(MetricValue).where(MetricValue.metric_code == m.code).order_by(MetricValue.created_at.desc()).limit(1)).scalar()
        if not mv or mv.display_value is None:
            continue
        out.append(
            {
                "code": m.code,
                "label": m.label,
                "value": float(mv.display_value),
                "display": _fmt(mv.display_value, m.decimals),
                "unit": UNIT.get(m.unit, m.unit),
                "previous": None if mv.previous_value is None else float(mv.previous_value),
                "formula": m.formula,
                "calcRunId": mv.calc_run_id,
                "at": mv.created_at.isoformat(),
            }
        )
    return out


def _num_pool(texts: list[str]) -> set[str]:
    pool: set[str] = set()
    for t in texts:
        for n in NUM.findall(t or ""):
            raw = n.replace(",", "")
            pool.add(raw)
            try:
                f = float(raw)
                pool.update({f"{f:g}", f"{f:.1f}", f"{f:.2f}", f"{f:.3f}", str(int(f)) if f == int(f) else raw})
            except ValueError:
                pass
    return pool


def _in_pool(raw: str, pool: set[str]) -> bool:
    if raw in pool:
        return True
    try:
        return f"{float(raw):g}" in pool
    except ValueError:
        return False


def verify_numbers(answer: str, allowed_texts: list[str], user_texts: list[str] | None = None) -> dict[str, Any]:
    """답변 숫자가 확정 수치 · 도구 결과 · 근거 중 어딘가에 있는지(쉼표 무시).
    질문에만 있는 숫자는 '사용자 제시값(userSupplied)' 으로 따로 표시한다 — 질문으로 숫자를 주입해 검증을 통과하지 못하게(8.4.4)."""
    pool = _num_pool(allowed_texts)
    upool = _num_pool(user_texts or [])
    unverified, supplied = [], []
    for n in NUM.findall(answer or ""):
        raw = n.replace(",", "")
        if len(raw.replace(".", "")) <= 1:
            continue  # 한 자리 숫자(순번 등)는 제외
        if _in_pool(raw, pool):
            continue
        if _in_pool(raw, upool):
            supplied.append(n)
            continue
        unverified.append(n)
    return {"checkCode": "numeric_provenance", "passed": not unverified, "unverified": unverified[:10], "userSupplied": supplied[:10]}


@router.post("/assist")
def ask(body: AskIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(require_resource("assist"))):
    q = body.question.strip()
    concepts = concepts_of(session, q)
    metrics = metrics_for(session, user, q, concepts)
    flt = graph_documents(concepts) if concepts else None
    as_of = session.get(Setting, "ui.as_of")
    cand = hybrid_search(session, q, doc_filter=flt, k=12)
    if flt is not None and not cand:
        flt, cand = None, hybrid_search(session, q, k=12)
    # 근거 선별(3.6) — 권한 · 부문 · 시점 · 의미 · 개념경로 게이팅 → 우선순위 → 범주 균형
    ranked = rank_evidence(session, cand, k=4, user=user, as_of=as_of.value if as_of else None, doc_filter=flt, query_terms=len(query_terms(q)))
    hits = ranked["hits"]
    evidence = [{"origin": h["origin"], "title": h["title"], "docClass": h["doc_class"], "page": h["page"], "sectionPath": h.get("section_path"), "category": h.get("category"), "priority": h.get("priority"), "text": h["text"][:400], "score": round(h["score"], 4)} for h in hits]
    facts = "\n".join(f"- [지표:{m['code']}] {m['label']} = {m['display']}{m['unit']} (calc_run {m['calcRunId'][:8]})" for m in metrics) or "(관련 지표 없음)"
    docs = "\n".join(f"- [문서:{e['title']}] p.{e['page'] or '-'}: {e['text'][:300]}" for e in evidence) or "(관련 근거 없음)"
    result: dict[str, Any] = {"question": q, "concepts": concepts, "metrics": metrics, "evidence": evidence, "graphFilter": flt, "evidenceRejected": len(ranked["rejected"]), "missingCategories": ranked["missingCategories"]}
    try:
        cfg = resolve(session, "query_assistant")
        system = (cfg.system_prompt or "너는 은행 데이터 질의 보조자다.") + "\n\n" + GUARD
        user_msg = (
            f"질문:\n{fence(q)}\n\n확정 수치(계산 커널 결과 — 이 값만 인용):\n{facts}\n\n근거 문서:\n{fence(docs)}\n\n"
            "규칙: 한국어 3~6문장. 숫자는 위 확정 수치나 calc_* 도구 결과만 쓴다(직접 계산 금지). 근거는 [지표:코드] 또는 [문서:제목]으로 표시한다. "
            "모르는 내용은 '확인된 데이터가 없습니다'라고 답한다. 인과를 단정하지 않는다."
        )
        out = chat_with_tools(session, cfg, [{"role": "system", "content": system}, {"role": "user", "content": user_msg}], purpose="assist")
        answer = out.get("answer") or ""
        tool_texts = [str(r["result"]) for r in out["tool_results"]]
        check = verify_numbers(answer, [facts, docs, *tool_texts], [q])
        result.update({"mode": "llm", "model": cfg.model, "answer": answer, "toolResults": out["tool_results"], "llmCallIds": out["call_ids"], "verification": check})
    except (LlmUnavailable, LlmError) as exc:
        lines = ["LLM 이 연결되지 않아 관련 확정 수치와 근거 문서만 정리했습니다."]
        if metrics:
            lines.append("관련 수치: " + " · ".join(f"{m['label']} {m['display']}{m['unit']}" for m in metrics[:4]))
        if evidence:
            lines.append("관련 근거: " + " · ".join(f"{e['title']}" + (f" p.{e['page']}" if e["page"] else "") for e in evidence[:3]))
        if not metrics and not evidence:
            lines.append("질문과 연결된 지표나 문서를 찾지 못했습니다. 지표 이름이나 상품·모형 이름을 넣어 다시 질문해 주세요.")
        result.update({"mode": "fallback", "answer": "\n".join(lines), "reason": str(exc)[:300], "verification": {"checkCode": "numeric_provenance", "passed": True, "unverified": []}})
    audit(session, user.emp_no, "assist.ask", "assist", None, {"question": q[:200], "mode": result["mode"], "metrics": [m["code"] for m in metrics], "verified": result["verification"]["passed"]}, client_ip(request))
    session.commit()
    return result
