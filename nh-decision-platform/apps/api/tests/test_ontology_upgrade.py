"""B.42 운영 DB 보강(`ontology-extraction-v2`) — 기존 DB(초기 프롬프트 · 이전 별칭)에서만 새 버전을 만들고 관리자 편집은 보존."""
from __future__ import annotations

import copy

from sqlalchemy import select

B42_ALIASES = {"정책서민금융", "서민금융 공급", "취약차주", "중·저신용", "중저신용", "가계대출 관리", "햇살론15", "햇살론유스", "햇살론 유스", "소기업 신용평가모형", "소기업 평가모형"}


def _old_aliases():
    from nhdip.seed import defs_core as C

    old = copy.deepcopy(C.ONTOLOGY_ALIASES)
    for entries in old.values():
        for key, aliases in entries.items():
            entries[key] = [a for a in aliases if a not in B42_ALIASES]
    return old


def _prepare(s, prompt_system: str, aliases: dict) -> None:
    """기존 DB 처럼 — 마지막 추출 프롬프트 문구 · 활성 스키마 별칭을 바꾸고 보강 적용 기록을 지운다."""
    from nhdip.models import OntologySchema, Prompt, Setting

    last = s.execute(select(Prompt).where(Prompt.agent_code == "ontology_extractor").order_by(Prompt.version.desc()).limit(1)).scalar()
    last.system, last.user_template = prompt_system, ""
    sc = s.execute(select(OntologySchema).where(OntologySchema.active)).scalar()
    sc.aliases = aliases
    st = s.get(Setting, "seed.applied_upgrades")
    st.value = [x for x in st.value if x != "ontology-extraction-v2"]
    s.flush()


def _state(s):
    from nhdip.models import OntologySchema, Prompt

    prompts = s.execute(select(Prompt).where(Prompt.agent_code == "ontology_extractor").order_by(Prompt.version)).scalars().all()
    active = s.execute(select(OntologySchema).where(OntologySchema.active)).scalars().all()
    return prompts, active


def test_extraction_upgrade_existing_db_and_admin_edits(db):
    from nhdip.models import OntologySchema
    from nhdip.seed import defs_core as C
    from nhdip.seed.run import ontology_extraction_upgrade

    # 1) 관리자가 프롬프트를 고치고 별칭 사전에서 키 하나를 지우고 자기 별칭을 넣은 기존 DB
    with db() as s:
        admin_aliases = _old_aliases()
        del admin_aliases["ProductGroup"]["햇살론"]
        admin_aliases["PolicyTheme"]["포용금융"].append("관리자별칭")
        _prepare(s, "관리자가 고친 추출 지시문", admin_aliases)
        before_prompts, before_active = _state(s)
        out: dict = {}
        ontology_extraction_upgrade(s, out)
        s.flush()
        prompts, active = _state(s)
        assert len(prompts) == len(before_prompts) and prompts[-1].system == "관리자가 고친 추출 지시문"  # 프롬프트는 그대로
        assert len(active) == 1 and active[0].version == before_active[0].version + 1  # 별칭만 더한 새 스키마 버전
        al = active[0].aliases
        assert "관리자별칭" in al["PolicyTheme"]["포용금융"] and "취약차주" in al["PolicyTheme"]["포용금융"]
        assert "햇살론" not in al["ProductGroup"]  # 관리자가 지운 키는 되살리지 않는다
        assert "소기업 신용평가모형" in al["RatingModel"]["CORP_MICRO"]
        assert out["ontology_extraction_upgrade"] == {"aliases_added": len(B42_ALIASES) - 3}  # 햇살론 별칭 3개는 키가 없어 제외
        old_v = s.get(OntologySchema, before_active[0].version)
        assert old_v is not None and not old_v.active
        # 1회만 — 다시 돌려도 바꾸지 않는다
        out2: dict = {}
        ontology_extraction_upgrade(s, out2)
        assert out2 == {} and len(_state(s)[1]) == 1
        s.rollback()

    # 2) 초기 프롬프트(v1 문구) 그대로인 기존 DB → 새 프롬프트 버전, 별칭 보강
    with db() as s:
        _prepare(s, C.EXTRACTOR_SYSTEM_V1, _old_aliases())
        before_prompts, before_active = _state(s)
        out = {}
        ontology_extraction_upgrade(s, out)
        s.flush()
        prompts, active = _state(s)
        assert len(prompts) == len(before_prompts) + 1 and prompts[-1].system == C.EXTRACTOR_SYSTEM and prompts[-1].created_by == "seed"
        assert active[0].aliases == C.ONTOLOGY_ALIASES  # 이전 별칭 + 이번 보강 = 시드 기본값
        assert out["ontology_extraction_upgrade"] == {"prompt": prompts[-1].version, "aliases_added": len(B42_ALIASES)}
        s.rollback()  # 시험 DB 는 다른 시험과 함께 쓰므로 되돌린다
