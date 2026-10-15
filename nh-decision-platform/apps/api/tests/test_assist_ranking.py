"""질의 패널 지표 찾기(B.44) — 업무 구성 파일 지표 정의 · 설정으로 골든셋 질의 순위를 DB 없이 재현한다."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

from nhdip.api.assist import metric_score, rank_metrics
from nhdip.graph.extraction import Resolver
from nhdip.sample.build import business_config
from nhdip.seed import defs_core as C

BIZ = business_config()  # 시연 업무 구성 파일(Phase O) — 지표 · 온톨로지 · 별칭은 여기서 온다
_SET = {s["key"]: s["value"] for s in BIZ["settings"]}


def _metrics():
    return [(m["code"], m["label"], m.get("sort") or 0) for m in BIZ["metrics"] if m.get("enabled", True)]


def _metric_synonyms() -> dict:
    return {**(C.SETTINGS["assist.metric_synonyms"][0] or {}), **(_SET.get("assist.metric_synonyms") or {})}


def _concepts(q: str) -> list[str]:
    """api.assist.concepts_of 와 같은 규칙(온톨로지 별칭 사전) — 플랫폼 + 업무 구성 스키마로."""
    o = BIZ["ontology"]
    r = Resolver(SimpleNamespace(classes=[*C.ONTOLOGY_CLASSES, *(o.get("classes") or [])], relations=[*C.ONTOLOGY_RELATIONS, *(o.get("relations") or [])],
                                 aliases={**C.ONTOLOGY_ALIASES, **(o.get("aliases") or {})}))
    low, found = q.lower(), []
    for amap in r.alias.values():
        for alias, key in amap.items():
            if len(alias) >= 2 and alias in low and key not in found:
                found.append(key)
    return found


def _rank(q: str) -> list[str]:
    return rank_metrics(_metrics(), q, _concepts(q), C.SETTINGS["assist.synonyms"][0], _metric_synonyms())


def test_golden_assist_questions_find_expected_metric_in_top8():
    """골든셋 질의(기존 4 + B.44 '차이' 2) — 기대 지표가 상위 8개(질의 패널 · 골든셋 평가 기준) 안에 든다."""
    path = os.path.join(os.path.dirname(__file__), "..", "src", "nhdip", "evals", "golden.json")
    with open(path, encoding="utf-8") as fh:
        cases = json.load(fh)["assist"]
    assert len(cases) >= 6
    for c in cases:
        top = _rank(c["question"])[:8]
        assert c["expect_metric"] in top, (c["question"], top)


def test_metric_synonym_phrase_beats_partial_label_match():
    """별칭 문구가 질문에 통째로 있으면 그 지표가 앞선다 — 지표명 일부만 맞는 지표보다."""
    q = "6B 대표값 차이는?"
    ranked = _rank(q)
    assert ranked.index("breach_gap_6b") < ranked.index("pd_mid_6b")
    # 조사가 끼어도('대표값의 차이') 별칭 문구로 본다 — 지표명이 더 많이 맞는 '실제부도율' 지표보다 앞선다
    assert _rank("6B 등급 실제부도율과 대표값의 차이는?")[0] == "breach_gap_6b"
    # 별칭 설정이 비면 이전 순위(지표명만) — 설정으로 되돌릴 수 있다
    plain = rank_metrics(_metrics(), q, _concepts(q), C.SETTINGS["assist.synonyms"][0], {})
    assert ranked.index("breach_gap_6b") <= plain.index("breach_gap_6b")


def test_upload_test_question_finds_breach_gap():
    """업로드 시험(apps/e2e/upload-agents.mjs) 질의 — '대표값 차이' 질문에 초과 폭 지표가 들어간다(LLM 이 직접 빼지 않게)."""
    q = "2026년 9월 기준 소기업 6B 등급 실제부도율과 예측부도율 대표값 차이는 얼마이고 최대값 이내인가요?"
    top = _rank(q)[:8]
    assert "breach_gap_6b" in top[:3] and "dr_6b" in top, top


def test_metric_score_ignores_bad_aliases():
    terms = ["차이"]
    assert metric_score("대표값 초과 폭", "breach_gap_6b", "차이", terms, ["", None, 3, " "]) == metric_score("대표값 초과 폭", "breach_gap_6b", "차이", terms)  # type: ignore[list-item]
