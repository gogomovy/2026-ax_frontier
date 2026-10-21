"""시드 실행 — 멱등. 이미 있는 행은 덮어쓰지 않는다(관리자 화면 수정 보존). 업무 자료 · 값은 넣지 않는다.

넣는 것: 관리자 계정 · 관리 조직 · 관리/공통 화면 · 플랫폼 설정 · 공통 규칙 · 시스템 온톨로지 · LLM 연결 · 에이전트 그룹 · 플랫폼 에이전트 ·
공통 흐름(그래프 투영 · 온톨로지 구축) · 공통 지식 컬렉션, 그리고 기본 업무 구성(seed/pack.py — 3개 부서 화면 · 업무 흐름 · 지표 산식 ·
화면 연결 · 업무 규칙 · 조직 · 화면 권한 · 값 없는 화면 틀).
넣지 않는 것: 데이터셋 정의 · 업무 자료 · 문서 · 계산값 — 원천 자료를 올리면 계산 커널이 지표 산식으로 계산한다.
"""
from __future__ import annotations

import copy
import logging
import os
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.events import audit
from nhdip.models import (
    Agent,
    AgentGroup,
    AppUser,
    KbCollection,
    LlmConnection,
    LlmProfile,
    OntologySchema,
    OrgUnit,
    Prompt,
    Rule,
    RuleVersion,
    Screen,
    ScreenGrant,
    Setting,
    Workflow,
    WorkflowNode,
    WorkflowTrigger,
    source,
)
from nhdip.security import encrypt_secret, hash_password

from . import defs_core as C
from . import defs_knowledge as K

log = logging.getLogger("nhdip.seed")


def seed_iam(s: Session, out: dict[str, Any]) -> None:
    from nhdip.orgs import recompute_levels

    n = 0
    for code, name, unit_type, parent, sort in C.ORGS:  # 상위 조직이 먼저 오도록 정렬된 정의
        o = s.get(OrgUnit, code)
        if not o:
            s.add(OrgUnit(code=code, name=name, level=1, unit_type=unit_type, parent_code=parent, sort=sort))
            n += 1
        elif o.unit_type is None:
            o.unit_type = unit_type
            if o.parent_code is None and parent:
                o.parent_code = parent
        s.flush()
    recompute_levels(s)
    old = s.get(Setting, "org.level_labels")
    if old:
        s.delete(old)
    s.flush()
    for sc in C.SCREENS:
        if not s.get(Screen, sc["code"]):
            s.add(Screen(**{k: v for k, v in sc.items() if k != "resources"}, active=True))
            n += 1
    s.flush()
    for org, screens in C.GRANTS.items():
        for sc in screens:
            if s.get(OrgUnit, org) is not None and not s.get(ScreenGrant, (org, sc)):
                s.add(ScreenGrant(org_code=org, screen_code=sc, granted_by="seed"))
    # 화면 리소스(API 권한 판정 기준)는 setting 에 둔다 — 관리자 화면에서 편집 · 업무 구성 파일이 업무 화면 리소스를 더한다
    res = {sc["code"]: sc.get("resources", []) for sc in C.SCREENS if sc.get("resources")}
    st_res = s.get(Setting, "screen.resources")
    if not st_res:
        s.add(Setting(key="screen.resources", value=res, description="화면 → 화면 API 리소스 (권한 판정)"))
    else:
        cur = dict(st_res.value or {})
        missing = {k: v for k, v in res.items() if k not in cur}
        if missing:
            st_res.value = {**cur, **missing}
    st = get_settings()
    if st.bootstrap_admin_password and not s.get(AppUser, st.bootstrap_admin_emp_no):
        s.add(AppUser(emp_no=st.bootstrap_admin_emp_no, name="시스템 관리자", password_hash=hash_password(st.bootstrap_admin_password), org_code=C.ADMIN_ORG, position="관리자", role="admin", data_admin=True, status="active", approved_by="bootstrap"))
        audit(s, "bootstrap", "user.bootstrap_admin", "user", st.bootstrap_admin_emp_no)
        out["admin"] = st.bootstrap_admin_emp_no
    out["iam"] = n


def seed_cfg(s: Session, out: dict[str, Any]) -> None:
    for key, (value, desc) in C.SETTINGS.items():
        if not s.get(Setting, key):
            s.add(Setting(key=key, value=copy.deepcopy(value), description=desc))
    for code, name, kind, desc, body in C.RULES:
        if not s.get(Rule, code):
            s.add(Rule(code=code, name=name, kind=kind, description=desc, active_version=1))
            s.flush()
            s.add(RuleVersion(rule_code=code, version=1, body=body, note="초기값", created_by="seed"))
    if not s.execute(select(OntologySchema)).first():
        s.add(OntologySchema(version=1, classes=C.ONTOLOGY_CLASSES, relations=C.ONTOLOGY_RELATIONS, aliases={}, interfaces=C.ONTOLOGY_INTERFACES, active=True,
                             note="시스템 온톨로지 — 데이터셋 · 지표 · 흐름 · 문서 계보. 업무 객체 유형은 업무 구성 파일 · 온톨로지 구축 제안으로"))
    # LLM 연결 · 프로필
    st = get_settings()
    conn = s.execute(select(LlmConnection).where(LlmConnection.name == "litellm")).scalar()
    if not conn:
        url = (st.llm_default_base_url or "").strip()
        conn = LlmConnection(name="litellm", base_url=url, api_key_enc=encrypt_secret(st.llm_default_api_key), active=bool(url), note=EXTERNAL_LLM_NOTE)
        s.add(conn)
        s.flush()
    else:
        _clear_bundled_litellm(conn)
    profiles = {}
    for name, model, is_default, extra in (("default", st.llm_default_model, True, {}), ("embedding", "", False, {})):
        p = s.execute(select(LlmProfile).where(LlmProfile.name == name)).scalar()
        if not p:
            p = LlmProfile(name=name, connection_id=conn.id, model=model, temperature=0.2 if name == "default" else None, max_tokens=1500 if name == "default" else None, timeout_sec=60, retries=2, tools_enabled=False, extra=extra, is_default=is_default)
            s.add(p)
            s.flush()
        profiles[name] = p.id
    for gcode, gname, gdesc, gsort in C.AGENT_GROUPS:
        if not s.get(AgentGroup, gcode):
            s.add(AgentGroup(code=gcode, name=gname, description=gdesc, sort=gsort))
    s.flush()
    for code, name, role, kind, profile, system in C.AGENTS:
        if not s.get(Agent, code):
            s.add(Agent(code=code, name=name, role=role, kind=kind, group_code=C.AGENT_GROUP_OF.get(code), profile_id=profiles.get(profile) if profile else None, override={}, enabled=True))
            s.flush()
            if kind == "llm" and system:
                s.add(Prompt(agent_code=code, version=1, system=system, user_template="", note="초기 프롬프트 (빈 user_template = 노드 기본 템플릿 사용)", created_by="seed"))
    s.flush()
    # 공통 흐름(그래프 투영 · 온톨로지 구축) — 업무 흐름은 업무 구성 파일로
    for w in C.WORKFLOWS_M:
        if s.get(Workflow, w["code"]):
            _upgrade_workflow(s, w)
            continue
        s.add(Workflow(code=w["code"], name=w["name"], description=w["description"], outputs=w["outputs"], sort=w["sort"], enabled=True))
        s.flush()
        for i, (key, name, impl, agent, cfg) in enumerate(w["nodes"], start=1):
            s.add(WorkflowNode(workflow_code=w["code"], seq=i * 10, key=key, name=name, impl=impl, agent_code=agent, enabled=True, config=cfg))
        for kind, target in w["triggers"]:
            s.add(WorkflowTrigger(workflow_code=w["code"], kind=kind, target=target, debounce_sec=w.get("debounce"), enabled=True))
    s.flush()
    out["cfg"] = "ok"


EXTERNAL_LLM_NOTE = "외부 LiteLLM(OpenAI 호환) 게이트웨이 — 관리자 [LLM 연동] 에서 주소 · 키 · 모델 입력. 키는 LiteLLM 가상 키 또는 마스터 키"
BUNDLED_LITELLM_URL = "http://litellm:4000"


def _clear_bundled_litellm(conn: Any, resolver: Any = None) -> bool:
    """예전 기본값(compose 내장 LiteLLM 주소)이 남아 있는데 그 컨테이너가 없으면 주소를 비우고 끈다 (B.36).
    키를 넣었거나 주소를 바꿨으면 건드리지 않는다. 내장 LiteLLM 을 켜서(COMPOSE_PROFILES=litellm) 이름이 풀리면 그대로 둔다."""
    import socket

    from nhdip.security import decrypt_secret

    if (conn.base_url or "").rstrip("/") != BUNDLED_LITELLM_URL:
        return False
    try:
        if decrypt_secret(conn.api_key_enc):
            return False
    except Exception:  # noqa: BLE001
        pass
    try:
        (resolver or socket.getaddrinfo)("litellm", 4000)
        return False
    except OSError:
        conn.base_url, conn.active, conn.note = "", False, EXTERNAL_LLM_NOTE
        return True


def _applied(s: Session, name: str) -> bool:
    """한 번만 적용하는 보강 — 적용 이름을 설정 seed.applied_upgrades 에 남긴다."""
    st = s.get(Setting, "seed.applied_upgrades")
    done = list(st.value) if st else []
    if name in done:
        return True
    done.append(name)
    if st:
        st.value = done
    else:
        s.add(Setting(key="seed.applied_upgrades", value=done, description="한 번만 적용하는 시드 보강 이름 (관리자가 이후 바꾼 값은 다시 덮지 않음)"))
    s.flush()
    return False


def _upgrade_workflow(s: Session, w: dict[str, Any]) -> None:
    """운영 중인 공통 흐름에 새로 정의된 노드 · 트리거만 추가(관리자가 바꾼 기존 노드 · 트리거는 유지)."""
    have = {n.key for n in s.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == w["code"])).scalars()}
    nodes = w["nodes"]
    tail = s.execute(select(func.max(WorkflowNode.seq)).where(WorkflowNode.workflow_code == w["code"])).scalar() or 0
    for i, (key, name, impl, agent, cfg) in enumerate(nodes):
        if key in have:
            continue
        nxt = next((n for n in nodes[i + 1 :] if n[0] in have), None)
        if nxt:
            nseq = s.execute(select(WorkflowNode.seq).where(WorkflowNode.workflow_code == w["code"], WorkflowNode.key == nxt[0])).scalar()
            seq = (nseq or 1000) - 5
        else:
            # 맨 뒤에 새로 붙는 노드가 여럿이면 정의 순서대로 이어 붙인다(같은 순번이면 실행 순서가 정해지지 않는다)
            tail += 10
            seq = tail
        s.add(WorkflowNode(workflow_code=w["code"], seq=seq, key=key, name=name, impl=impl, agent_code=agent, enabled=True, config=cfg))
    trig = {(t.kind, t.target) for t in s.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == w["code"])).scalars()}
    for kind, target in w["triggers"]:
        if (kind, target) not in trig and kind != "cron":
            s.add(WorkflowTrigger(workflow_code=w["code"], kind=kind, target=target, debounce_sec=w.get("debounce"), enabled=True))


def backfill_section_paths(s: Session, out: dict[str, Any]) -> None:
    """운영 DB 청크에 문서 구조 경로(section_path)를 채운다 — 1회, 비어 있는 청크만 (3.2.3)."""
    if _applied(s, "section-path-v1"):
        return
    from nhdip.data.documents import section_paths

    n = 0
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in s.execute(select(t.document).where(t.document.is_current)).scalars():
            chunks = s.execute(select(t.chunk).where(t.chunk.document_id == d.id).order_by(t.chunk.seq)).scalars().all()
            if not chunks or any(c.section_path for c in chunks):
                continue
            for c, sec in zip(chunks, section_paths([c.text for c in chunks])):
                if sec:
                    c.section_path = sec[:500]
                    n += 1
    out["section_paths"] = n


def has_business_data(s: Session) -> bool:
    """확정된 데이터셋 버전이 하나라도 있는지."""
    return any(s.execute(select(source(o).version.id).where(source(o).version.is_current).limit(1)).first() for o in ("bank", "ext"))


def hardening_upgrade(s: Session, out: dict[str, Any]) -> None:
    """B.32 점검 보완 — 기존 DB 의 사전형 설정에 새 키만 채운다(관리자가 바꾼 값은 보존, 매 기동 멱등)."""
    added = {}
    for key in ("agents.llm_judge", "orchestrator.policy", "auth.rate_limits", "retention.policy", "privacy.policy", "calc.unit_check"):
        st = s.get(Setting, key)
        if st is None or not isinstance(st.value, dict) or key not in C.SETTINGS:
            continue
        missing = {k: v for k, v in C.SETTINGS[key][0].items() if k not in st.value}
        if missing:
            st.value = {**st.value, **missing}
            added[key] = sorted(missing)
    out["hardening_upgrade"] = added


# 이전 관리자 메뉴 기본값(묶음 · 이름) — 관리자가 바꾸지 않은 화면만 새 묶음으로 옮긴다 (Phase C · Q104)
_OLD_ADMIN_SECTIONS = {"관리자", "관리자 · 모니터링"}
_OLD_ADMIN_LABELS = {"ADMIN_HOME": "시스템 상태", "ADMIN_AGENTS": "에이전트", "ADMIN_WORKFLOWS": "워크플로우"}


def phase_m_upgrade(s: Session, out: dict[str, Any]) -> None:
    """Phase M(요구사항 §30 · §31) — 1회. ① 그룹이 비어 있는 에이전트에 기본 그룹 ② 프롬프트 표준 새 판 — 최신 판이 이전 시드 문구 그대로인 에이전트만(Q184)
    ③ 오케스트레이터 경로 지정 제외에 구축 워크플로."""
    if _applied(s, "phase-m-v1"):
        return
    from nhdip.models import AnalysisAgent

    dyn = {a.code for a in s.execute(select(AnalysisAgent)).scalars()}
    n_group = 0
    for a in s.execute(select(Agent).where(Agent.group_code.is_(None))).scalars():
        g = C.AGENT_GROUP_OF.get(a.code) or ("analysis" if a.code in dyn or a.code.startswith("an_") else None)
        if g and s.get(AgentGroup, g):
            a.group_code = g
            n_group += 1
    new_sys = {code: system for code, _n, _r, kind, _p, system in C.AGENTS if kind == "llm" and system}
    n_prompt = 0
    for code, old in C.PROMPT_SEED_V1.items():
        a = s.get(Agent, code)
        if a is None or code not in new_sys:
            continue
        latest = s.execute(select(Prompt).where(Prompt.agent_code == code).order_by(Prompt.version.desc()).limit(1)).scalar()
        if latest is None or (latest.system or "").strip() != old.strip():
            continue
        s.add(Prompt(agent_code=code, version=latest.version + 1, system=new_sys[code], user_template=latest.user_template or "", note="Phase M 프롬프트 표준(역할 · 입력 · 규칙 · 출력 · 금지 · 예시) — 이전 판으로 되돌리려면 버전 이력 '적용'", created_by="seed"))
        if a.prompt_version in (None, latest.version):
            a.prompt_version = latest.version + 1
        n_prompt += 1
    st = s.get(Setting, "orchestrator.policy")
    if st is not None and isinstance(st.value, dict):
        ex = list(st.value.get("route_exclude") or ["wf_graph_projection"])
        if "wf_ontology_build" not in ex:
            st.value = {**st.value, "route_exclude": [*ex, "wf_ontology_build"]}
    s.flush()
    out["phase_m"] = {"groups_assigned": n_group, "prompts_upgraded": n_prompt}


def phase_m_stages_upgrade(s: Session, out: dict[str, Any]) -> None:
    """Phase M — 1회. 관리자 [파이프라인] 단계 설정(pipeline.stages)에 새 구현을 더한다(어느 단계에도 없는 구현만)."""
    if _applied(s, "phase-m-stages-v1"):
        return
    st = s.get(Setting, "pipeline.stages")
    if st is None or not isinstance(st.value, list):
        return
    stages = copy.deepcopy(st.value)
    have = {i for g in stages if isinstance(g, dict) for i in g.get("impls") or []}
    added = []
    for pos, d in enumerate(C.PIPELINE_STAGES):
        missing = [i for i in d["impls"] if i not in have]
        if not missing:
            continue
        cur = next((g for g in stages if isinstance(g, dict) and g.get("key") == d["key"]), None)
        if cur is None:
            stages.insert(min(pos, len(stages)), {**copy.deepcopy(d), "impls": missing})
        else:
            cur["impls"] = [*(cur.get("impls") or []), *missing]
        added += missing
    if added:
        st.value = stages
        s.flush()
        out["pipeline_stages_added"] = added


def admin_ia_upgrade(s: Session, out: dict[str, Any]) -> None:
    """관리자 정보 구조(Phase C · ADM-01) — 1회. 관리자 화면을 묶음 6개로(이전 기본 묶음인 화면만), 이전 기본 이름만 새 이름으로."""
    if _applied(s, "admin-ia-v1"):
        return
    moved = 0
    for spec in C.SCREENS:
        if spec.get("kind") != "admin":
            continue
        sc = s.get(Screen, spec["code"])
        if sc is None or sc.section not in _OLD_ADMIN_SECTIONS:
            continue
        sc.section, sc.sort = spec["section"], spec["sort"]
        if spec.get("match") is not None:
            sc.match = spec["match"]
        if _OLD_ADMIN_LABELS.get(sc.code) == sc.label:
            sc.label = spec["label"]
        moved += 1
    out["admin_ia_upgrade"] = moved


def admin_ia_v2_upgrade(s: Session, out: dict[str, Any]) -> None:
    """관리자 메뉴 7묶음(Phase P · ADM2-04) — 1회. Phase C 기본 묶음에 있는 관리자 화면만 새 묶음 · 정렬로(관리자가 바꾼 묶음은 그대로)."""
    if _applied(s, "admin-ia-v2"):
        return
    moved = 0
    for spec in C.SCREENS:
        if spec.get("kind") != "admin":
            continue
        sc = s.get(Screen, spec["code"])
        if sc is None or sc.section not in C.ADMIN_SECTIONS_V1:
            continue
        if (sc.section, sc.sort) != (spec["section"], spec["sort"]):
            sc.section, sc.sort = spec["section"], spec["sort"]
            moved += 1
    out["admin_ia_v2"] = moved


def analysis_agents_team_upgrade(s: Session, out: dict[str, Any]) -> None:
    """분석 에이전트 팀 데이터(Phase P · TDB) — 1회. 이미 승인된 분석 에이전트의 노드 사슬(팀 데이터 · 근거 검색)과 팀 · 공통 조건을 맞춘다."""
    if _applied(s, "analysis-agents-team-v1"):
        return
    from nhdip.analysis_agents.lifecycle import sync_nodes
    from nhdip.models import AnalysisAgent

    n = 0
    for a in s.execute(select(AnalysisAgent).where(AnalysisAgent.status.in_(("active", "paused")))).scalars():
        try:
            with s.begin_nested():
                n += int(sync_nodes(s, a))
        except Exception:  # noqa: BLE001 — 한 에이전트 보강 실패가 기동을 막지 않는다
            log.exception("analysis agent sync failed (%s)", a.code)
    out["analysis_agents_team"] = n


def rename_upgrades(s: Session, out: dict[str, Any]) -> None:
    """화면 이름 바꾸기(이전 기본 이름일 때만 · 관리자가 바꾼 이름은 보존) — 1회씩."""
    for name, code, old, new in (("assist-rename-v1", "ADMIN_KNOWLEDGE", "질문하기 색인", "AI 어시스턴트 색인"), ("analysis-builder-rename-v1", "ANALYSIS_BUILDER", "분석 만들기", "분석 에이전트 만들기")):
        if _applied(s, name):
            continue
        sc = s.get(Screen, code)
        if sc is not None and sc.label == old:
            sc.label = new
            out[name] = 1


def search_3way_upgrade(s: Session, out: dict[str, Any]) -> None:
    """3-way 검색 구성(Phase H · 설계 §24) — 1회. knowledge.search.backend 가 예전 기본값 'pg' 이면 'auto' 로."""
    if _applied(s, "search-3way-v1"):
        return
    st = s.get(Setting, "knowledge.search")
    if st is not None and isinstance(st.value, dict) and str(st.value.get("backend", "pg")).strip().lower() == "pg":
        st.value = {**st.value, "backend": "auto"}
        out["search_3way_upgrade"] = 1


def admin_counts_upgrade(s: Session, out: dict[str, Any]) -> None:
    """관리자 처리 대기 건수(Phase E · NAV-04 · Q122) — 1회. 관리자 화면에 건수 키를 단다(관리자가 지정한 화면은 그대로)."""
    if _applied(s, "admin-counts-v1"):
        return
    done = []
    for spec in C.SCREENS:
        key = spec.get("count_key")
        if spec.get("kind") != "admin" or not key:
            continue
        sc = s.get(Screen, spec["code"])
        if sc is not None and not sc.count_key:
            sc.count_key = key
            done.append(sc.code)
    out["admin_counts_upgrade"] = done


def steward_inbox_upgrade(s: Session, out: dict[str, Any]) -> None:
    """§40 STW — 1회. [자료 올리기] 메뉴에 데이터 책임자 승인함 건수를 달고(관리자가 바꾼 건수 키는 그대로),
    이미 승인된 분석 에이전트 흐름에 변화 감지 단계를 더한다(새 승인은 lifecycle._nodes 가 넣는다)."""
    if _applied(s, "steward-inbox-v1"):
        return
    sc = s.get(Screen, "KNOWLEDGE_UPLOAD")
    if sc is not None and not sc.count_key:
        sc.count_key = "stewardTodo"
    from nhdip.models import AnalysisAgent

    added = []
    for a in s.execute(select(AnalysisAgent).where(AnalysisAgent.status.in_(("active", "paused")), AnalysisAgent.workflow_code.is_not(None))).scalars():
        nodes = s.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == a.workflow_code).order_by(WorkflowNode.seq)).scalars().all()
        if not nodes or any(n.impl == "detect_changes" for n in nodes):
            continue
        comp = next((n for n in nodes if n.impl == "compute_metrics"), None)
        after = next((n for n in nodes if comp is not None and n.seq > comp.seq), None)
        if comp is None:
            continue
        seq = (comp.seq + after.seq) // 2 if after is not None and after.seq - comp.seq > 1 else comp.seq + 1
        s.add(WorkflowNode(workflow_code=a.workflow_code, seq=seq, key="detect", name="변화 감지", impl="detect_changes", agent_code="change_detector", enabled=True, config={"optional": True}))
        added.append(a.workflow_code)
    out["steward_inbox_upgrade"] = {"count_key": bool(sc is not None and sc.count_key == "stewardTodo"), "detect_added": added}


def data_admin_upgrade(s: Session, out: dict[str, Any]) -> None:
    """Phase J (DEL-01 · Q143) — 데이터 관리자가 한 명도 없으면 부트스트랩 관리자를 지정(1회)."""
    if _applied(s, "data-admin-v1"):
        return
    if s.execute(select(AppUser.emp_no).where(AppUser.data_admin, AppUser.role == "admin").limit(1)).first():
        return
    u = s.get(AppUser, get_settings().bootstrap_admin_emp_no)
    if u is not None and u.role == "admin":
        u.data_admin = True
        audit(s, "seed", "user.data_admin", "user", u.emp_no, {"granted": True, "reason": "Phase J 데이터 관리자 초기 지정"})
        out["data_admin"] = u.emp_no


def seed_knowledge(s: Session, out: dict[str, Any]) -> None:
    """AI 어시스턴트 통합 지식 색인(Phase D) — 공통 컬렉션(없는 코드만) + 분석 결과 색인 대조. 업무 컬렉션은 업무 구성 파일로."""
    from nhdip.knowledge.maintenance import reconcile

    added = 0
    for c in K.COLLECTIONS:
        if s.get(KbCollection, c["code"]) is None:
            s.add(KbCollection(**c))
            added += 1
    s.flush()
    try:
        with s.begin_nested():
            stats = reconcile(s)
        out["knowledge"] = {"collections_added": added, **stats.as_dict()}
    except Exception as exc:  # noqa: BLE001 — 색인 실패가 기동을 막지 않는다(워커 대조가 다시 시도)
        log.exception("지식 색인 시드 실패")
        out["knowledge"] = {"collections_added": added, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def run_seed(s: Session, with_precompute: bool = False) -> dict[str, Any]:  # noqa: ARG001 — 업무 흐름이 없으므로 선계산 없음(호출 호환)
    out: dict[str, Any] = {}
    seed_iam(s, out)
    seed_cfg(s, out)
    s.flush()
    backfill_section_paths(s, out)
    hardening_upgrade(s, out)
    phase_m_upgrade(s, out)
    phase_m_stages_upgrade(s, out)
    admin_ia_upgrade(s, out)
    admin_ia_v2_upgrade(s, out)
    rename_upgrades(s, out)
    admin_counts_upgrade(s, out)
    data_admin_upgrade(s, out)
    analysis_agents_team_upgrade(s, out)
    s.flush()
    steward_inbox_upgrade(s, out)
    s.flush()
    # 기본 업무 구성(3개 부서 화면 · 흐름 · 지표 산식 · 화면 연결 · 조직 · 화면 권한 — 값 없음). 값은 올린 원천 자료로 계산한다
    from .pack import seed_business_pack

    seed_business_pack(s, out)
    # 업무 구성 파일 올리기 화면은 없앴다(구성은 제품에 포함) — 예전 DB 의 메뉴 항목을 지운다
    old = s.get(Screen, "ADMIN_BUSINESS_CONFIG")
    if old is not None:
        s.execute(sql_delete(ScreenGrant).where(ScreenGrant.screen_code == old.code))
        s.delete(old)
    s.flush()
    seed_knowledge(s, out)
    s.flush()
    search_3way_upgrade(s, out)
    s.commit()
    _ = func
    return out
