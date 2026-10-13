"""임베딩 모델별 코사인 거리 임계값 보정 (설계 §21.15 · Q119).

코사인 거리의 눈금은 모델마다 다르다(같은 '관련 있음'이 한 모델에서는 0.3, 다른 모델에서는 0.5). 그래서 검색의 의미 기준 `max_cosine_distance` 를
숫자 하나로 고정하면 모델을 바꿀 때마다 엉뚱한 글이 섞이거나 정답이 걸러진다. 이 모듈은 **지금 쓰는 임베딩 모델**로 두 가지를 재어 임계값을 추천한다.

- 음성: 은행 데이터와 상관없는 질문(`OFF_TOPIC_PROBES`)이 색인에서 찾는 가장 가까운 글의 거리 — 이보다 가까우면 엉뚱한 글이 섞인다.
- 양성: 색인된 제목(질문과 같은 짧은 글)이 색인에서 찾는 가장 가까운 글의 거리 — 이보다 멀어야 정답이 걸러지지 않는다.

추천값 = 음성 하위 25% 거리 − 0.02. 음성과 양성이 겹쳐 가를 수 없으면 `confident=False` 로 두고 값을 바꾸지 않는다.
자동으로 적용하지 않는다 — 관리자가 결과(분포)를 보고 [적용]하거나 CLI `kb-calibrate --apply`.
"""
from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from nhdip.llm import embed, resolve
from nhdip.models import Setting

from .access import setting_dict
from .defaults import SEARCH_DEFAULT
from .maintenance import embedding_agent

CALIBRATION_KEY = "knowledge.calibration"
OFF_TOPIC_PROBES = [
    "오늘 점심으로 뭘 먹을까요?", "프로야구 어제 경기 결과 알려줘", "고양이 사료 추천해 주세요", "비 오는 날 우산 없이 가는 방법", "서울에서 부산까지 KTX 요금이 얼마인가요",
    "안녕하세요", "테스트", "날씨 알려줘", "주말에 갈 만한 여행지 추천", "맛있는 김치찌개 끓이는 법", "요즘 인기 있는 드라마 뭐야", "스마트폰 배터리 오래 쓰는 법",
    "강아지 산책 시간은 얼마가 좋아요", "커피 한 잔 하실래요", "헬스장 회원권 가격 비교", "운전면허 갱신 방법",
]
MIN_THRESHOLD, MAX_THRESHOLD = 0.15, 0.85
MARGIN = 0.02


def _pct(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))]


def _nearest(session: Session, vec: list[float], model: str, dim: int) -> float | None:
    v = "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
    return session.execute(
        text("SELECT min(embedding <=> CAST(:v AS vector)) FROM app.kb_chunk WHERE embedding IS NOT NULL AND embedding_model = :m AND vector_dims(embedding) = :d"),
        {"v": v, "m": model, "d": dim},
    ).scalar()


def decide(positives: list[float], negatives: list[float]) -> dict[str, Any]:
    """거리 분포 → 추천 임계값 (순수 함수 — 시험하기 쉽게 분리)."""
    pos, neg = sorted(positives), sorted(negatives)
    out: dict[str, Any] = {
        "positives": {"n": len(pos), "median": round(statistics.median(pos), 3) if pos else None, "p90": round(_pct(pos, 0.9), 3) if pos else None},
        "negatives": {"n": len(neg), "min": round(neg[0], 3) if neg else None, "p25": round(_pct(neg, 0.25), 3) if neg else None, "median": round(statistics.median(neg), 3) if neg else None},
    }
    if len(neg) < 5 or len(pos) < 5:
        return {**out, "suggested": None, "confident": False, "note": "보정 재료가 부족합니다(임베딩된 청크와 제목이 더 필요)"}
    suggested = round(min(MAX_THRESHOLD, max(MIN_THRESHOLD, _pct(neg, 0.25) - MARGIN)), 2)
    floor = _pct(pos, 0.9)
    confident = suggested > floor + 0.03
    note = "엉뚱한 질문과 정상 질문의 거리가 나뉘어 추천값을 쓸 수 있습니다" if confident else "엉뚱한 질문과 정상 질문의 거리가 겹칩니다 — 추천값을 쓰지 말고 현재 값을 유지하세요(검색 진단으로 직접 확인)"
    return {**out, "suggested": suggested, "confident": confident, "note": note}


def calibrate(session: Session, *, sample: int = 40, seed: int = 7) -> dict[str, Any]:
    """현재 임베딩 모델 · 색인 기준으로 추천 임계값을 계산한다(쓰기 없음). 임베딩 모델 미설정 · 색인 없음은 LlmUnavailable/ValueError."""
    llm = resolve(session, embedding_agent(session))
    rows = session.execute(
        text("SELECT DISTINCT title FROM app.kb_chunk WHERE embedding IS NOT NULL AND embedding_model = :m AND char_length(title) >= 10 AND collection_code NOT LIKE 'admin.%'"),
        {"m": llm.model},
    ).scalars().all()
    chunks = session.execute(text("SELECT count(*) FROM app.kb_chunk WHERE embedding IS NOT NULL AND embedding_model = :m"), {"m": llm.model}).scalar() or 0
    if not rows or not chunks:
        raise ValueError("현재 임베딩 모델로 임베딩된 청크가 없습니다 — 워커가 임베딩을 채운 뒤 다시 하세요")
    rnd = random.Random(seed)
    titles = rnd.sample(rows, min(sample, len(rows)))
    vecs = embed(session, llm, titles) + embed(session, llm, OFF_TOPIC_PROBES)
    dim = len(vecs[0])
    d1 = [_nearest(session, v, llm.model, dim) for v in vecs]
    pos = [d for d in d1[: len(titles)] if d is not None]
    neg = [d for d in d1[len(titles):] if d is not None]
    current = float(setting_dict(session, "knowledge.search", SEARCH_DEFAULT)["max_cosine_distance"])
    return {"model": llm.model, "dim": dim, "chunks": int(chunks), "current": current, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **decide(pos, neg)}


def apply_calibration(session: Session, result: dict[str, Any], by: str | None = None) -> dict[str, Any]:
    """추천값을 검색 설정에 반영하고 보정 기록을 남긴다. 확신 없는 결과는 거부(ValueError)."""
    if not result.get("confident") or result.get("suggested") is None:
        raise ValueError(result.get("note") or "확신할 수 없는 보정 결과는 적용하지 않습니다")
    cur = session.get(Setting, "knowledge.search")
    value = {**(cur.value if cur is not None and isinstance(cur.value, dict) else {}), "max_cosine_distance": result["suggested"]}
    if cur is None:
        session.add(Setting(key="knowledge.search", value=value, description="질문하기 하이브리드 검색 설정"))
    else:
        cur.value = value
    # 문서 근거 선별(evidence.policy)도 같은 의미 기준을 쓴다 — 한쪽만 바꾸면 청크와 문서의 기준이 어긋난다
    ev = session.get(Setting, "evidence.policy")
    if ev is None:
        session.add(Setting(key="evidence.policy", value={"max_cosine_distance": result["suggested"]}, description="근거 선별 정책(질문하기 보정으로 생성 — 나머지 항목은 기본값)"))
    elif isinstance(ev.value, dict):
        ev.value = {**ev.value, "max_cosine_distance": result["suggested"]}
    rec = {**result, "appliedBy": by, "appliedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    s2 = session.get(Setting, CALIBRATION_KEY)
    if s2 is None:
        session.add(Setting(key=CALIBRATION_KEY, value=rec, description="임베딩 모델별 거리 임계값 보정 기록(마지막 적용) — 직접 고치지 않는다"))
    else:
        s2.value = rec
    session.flush()
    return rec


def calibrated_model(session: Session) -> str | None:
    s = session.get(Setting, CALIBRATION_KEY)
    return str(s.value.get("model")) if s is not None and isinstance(s.value, dict) and s.value.get("model") else None
