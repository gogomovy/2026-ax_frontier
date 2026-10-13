"""시드 실행 — 멱등. 이미 있는 행은 덮어쓰지 않는다(관리자 화면 수정 보존)."""
from __future__ import annotations

import copy
import glob
import json
import logging
import os
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.data.documents import ingest_document
from nhdip.events import audit, emit
from nhdip.models import (
    Agent,
    AppUser,
    Dataset,
    KbCollection,
    LlmConnection,
    LlmProfile,
    Metric,
    OntologySchema,
    OrgUnit,
    Prompt,
    Rule,
    RuleVersion,
    Screen,
    ScreenGrant,
    Setting,
    ViewArtifact,
    ViewBinding,
    Workflow,
    WorkflowNode,
    WorkflowTrigger,
    source,
)
from nhdip.security import encrypt_secret, hash_password
from nhdip.views.store import publish

from . import defs_branch as B
from . import defs_contracts as DC
from . import defs_core as C
from . import defs_data as D
from . import defs_knowledge as K
from . import defs_real as R

log = logging.getLogger("nhdip.seed")
HERE = os.path.dirname(__file__)


def _screens_dir() -> str:
    return get_settings().seed_dir or os.path.join(HERE, "screens")


def seed_iam(s: Session, out: dict[str, Any]) -> None:
    from nhdip.orgs import recompute_levels

    n = 0
    upgraded = 0
    for code, name, unit_type, parent, sort in C.ORGS:  # 상위 조직이 먼저 오도록 정렬된 정의
        o = s.get(OrgUnit, code)
        if not o:
            s.add(OrgUnit(code=code, name=name, level=1, unit_type=unit_type, parent_code=parent, sort=sort))
            n += 1
        elif o.unit_type is None:
            # 유형 도입 이전(부 > 국 > 팀) 조직 — 유형 지정 + 새 상위(본부)에 연결. 관리자가 지정한 유형은 건드리지 않는다
            o.unit_type = unit_type
            if o.parent_code is None and parent:
                o.parent_code = parent
            upgraded += 1
        s.flush()
    recompute_levels(s)
    old = s.get(Setting, "org.level_labels")
    if old:
        s.delete(old)
    if upgraded:
        out["org_upgraded"] = upgraded
    s.flush()
    for sc in C.SCREENS:
        if not s.get(Screen, sc["code"]):
            s.add(Screen(**{k: v for k, v in sc.items() if k != "resources"}, active=True))
            n += 1
    s.flush()
    for org, screens in C.GRANTS.items():
        for sc in screens:
            if not s.get(ScreenGrant, (org, sc)):
                s.add(ScreenGrant(org_code=org, screen_code=sc, granted_by="seed"))
    # 화면 리소스(API 권한 판정 기준)는 setting 에 둔다 — 관리자 화면에서 편집
    res = {sc["code"]: sc.get("resources", []) for sc in C.SCREENS if sc.get("resources")}
    if not s.get(Setting, "screen.resources"):
        s.add(Setting(key="screen.resources", value=res, description="화면 → 화면 API 리소스 (권한 판정)"))
    st = get_settings()
    if st.bootstrap_admin_password and not s.get(AppUser, st.bootstrap_admin_emp_no):
        s.add(AppUser(emp_no=st.bootstrap_admin_emp_no, name="시스템 관리자", password_hash=hash_password(st.bootstrap_admin_password), org_code="T911", position="관리자", role="admin", data_admin=True, status="active", approved_by="bootstrap"))
        audit(s, "bootstrap", "user.bootstrap_admin", "user", st.bootstrap_admin_emp_no)
        out["admin"] = st.bootstrap_admin_emp_no
    demo_pw = os.environ.get("DEMO_USER_PASSWORD", "")
    if demo_pw:
        for emp, name, org, pos in (("20250001", "이수정", "T111", "과장"), ("20250002", "박현우", "T211", "차장"), ("20250003", "최지훈", "001068", "대리")):
            if not s.get(AppUser, emp):
                s.add(AppUser(emp_no=emp, name=name, password_hash=hash_password(demo_pw), org_code=org, position=pos, role="user", status="active", approved_by="seed"))
        out["demo_users"] = 3
    out["iam"] = n


def seed_cfg(s: Session, out: dict[str, Any]) -> None:
    for key, (value, desc) in C.SETTINGS.items():
        if not s.get(Setting, key):
            s.add(Setting(key=key, value=value, description=desc))
    for code, name, kind, desc, body in [*C.RULES, DC.RULE, DC.RULE_IMPACT, *B.RULES, *R.RULES]:
        if not s.get(Rule, code):
            s.add(Rule(code=code, name=name, kind=kind, description=desc, active_version=1))
            s.flush()
            s.add(RuleVersion(rule_code=code, version=1, body=body, note="초기값", created_by="seed"))
    if not s.execute(select(OntologySchema)).first():
        s.add(OntologySchema(version=2, classes=C.ONTOLOGY_CLASSES, relations=C.ONTOLOGY_RELATIONS, aliases=C.ONTOLOGY_ALIASES, active=True, note="NH-DIO v2 (설계 §19.3)"))
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
    for code, name, role, kind, profile, system in C.AGENTS:
        if not s.get(Agent, code):
            s.add(Agent(code=code, name=name, role=role, kind=kind, profile_id=profiles.get(profile) if profile else None, override={}, enabled=True))
            s.flush()
            if kind == "llm" and system:
                s.add(Prompt(agent_code=code, version=1, system=system, user_template="", note="초기 프롬프트 (빈 user_template = 노드 기본 템플릿 사용)", created_by="seed"))
    s.flush()
    # 데이터셋 정의
    for d in [*D.DATASETS, DC.DATASET, *B.DATASETS]:
        if not s.get(Dataset, d["code"]):
            s.add(Dataset(**d))
    s.flush()
    # 품질 규칙 보강 (1.4) — 업그레이드 이름별 1회
    done_s = s.get(Setting, "seed.applied_upgrades")
    done = list(done_s.value) if done_s else []
    for name, per_ds in D.QUALITY_UPGRADES.items():
        if name in done:
            continue
        for code, rules in per_ds.items():
            ds = s.get(Dataset, code)
            if not ds:
                continue
            have = {(r.get("rule"), r.get("column")) for r in ds.quality_rules or []}
            add = [r for r in rules if (r["rule"], r["column"]) not in have]
            if add:
                ds.quality_rules = [*(ds.quality_rules or []), *add]
        done.append(name)
    if done_s:
        done_s.value = done
    else:
        s.add(Setting(key="seed.applied_upgrades", value=done, description="한 번만 적용하는 시드 보강 이름 (관리자가 이후 바꾼 값은 다시 덮지 않음)"))
    s.flush()
    # 워크플로우 · 노드 · 트리거
    for w in [*D.WORKFLOWS, *B.WORKFLOWS]:
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
    for m in [*D.metrics(), *DC.metrics(), *B.metrics()]:
        cur = s.get(Metric, m["code"])
        if not cur:
            s.add(Metric(**m))
        elif m["enabled"] and not cur.enabled and (cur.description or "").startswith("요구사항 Q10"):
            # Q10 추천안 — 등급 집계 기준 AUROC·AR·K-S 활성화(관리자가 끈 지표는 설명이 바뀌므로 건드리지 않음)
            cur.enabled, cur.description = True, m["description"]
    _goal_engine_upgrade(s)
    _psi_bands_upgrade(s)
    if not _applied(s, "adapters-v1"):
        # 원본 보고서 어댑터 설정 — 비어 있는 parser 키만 채운다(관리자 편집 보존)
        for code, cfg in D.PARSERS.items():
            ds = s.get(Dataset, code)
            if ds is not None:
                ds.parser = {**cfg, **(ds.parser or {})}
    if not s.execute(select(ViewBinding)).first():
        for b in [*D.bindings(), *B.bindings()]:
            s.add(ViewBinding(**b, enabled=True))
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


def _goal_engine_upgrade(s: Session) -> None:
    """Phase 2.6 목표 추천 엔진(Q28) — 운영 DB 의 규칙 · 지표가 이전 기본값 그대로일 때만 새 정의로 올린다."""
    if _applied(s, "goal-engine-v2"):
        return
    rule = s.get(Rule, "GOAL_REC_POLICY")
    if rule:
        cur = s.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
        if cur and cur.body == DC.RULE_BODY_V1:
            last = s.execute(select(RuleVersion.version).where(RuleVersion.rule_code == rule.code).order_by(RuleVersion.version.desc()).limit(1)).scalar() or 1
            s.add(RuleVersion(rule_code=rule.code, version=last + 1, body=DC.RULE_BODY_V2, note="Q28 추천안: 기조 · 추세 · 안전 마진 (목표 추천 엔진)", created_by="seed"))
            rule.active_version, rule.name, rule.description = last + 1, DC.RULE[1], DC.RULE[3]
    m = s.get(Metric, "corp_growth_rec")
    if m and m.formula == "RANGE_REC" and (m.args or {}).get("ceiling", {}).get("path") == "corp_loan_growth.ceiling":
        new = next(x for x in DC.metrics() if x["code"] == "corp_growth_rec")
        m.formula, m.args, m.description = new["formula"], new["args"], new["description"]
    s.flush()


def _upgrade_workflow(s: Session, w: dict[str, Any]) -> None:
    """운영 중인 워크플로우에 새로 정의된 노드·트리거만 추가(관리자가 바꾼 기존 노드·트리거는 유지)."""
    have = {n.key for n in s.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == w["code"])).scalars()}
    nodes = w["nodes"]
    for i, (key, name, impl, agent, cfg) in enumerate(nodes):
        if key in have:
            continue
        # 정의상 다음 노드 바로 앞 순번으로 끼워 넣는다
        nxt = next((n for n in nodes[i + 1 :] if n[0] in have), None)
        seq = 999
        if nxt:
            nseq = s.execute(select(WorkflowNode.seq).where(WorkflowNode.workflow_code == w["code"], WorkflowNode.key == nxt[0])).scalar()
            seq = (nseq or 1000) - 5
        s.add(WorkflowNode(workflow_code=w["code"], seq=seq, key=key, name=name, impl=impl, agent_code=agent, enabled=True, config=cfg))
    trig = {(t.kind, t.target) for t in s.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_code == w["code"])).scalars()}
    for kind, target in w["triggers"]:
        if (kind, target) not in trig and kind != "cron":  # cron 은 관리자 설정을 존중(이미 추가된 경우 중복 방지)
            s.add(WorkflowTrigger(workflow_code=w["code"], kind=kind, target=target, debounce_sec=w.get("debounce"), enabled=True))


def seed_contracts(s: Session, out: dict[str, Any]) -> None:
    from nhdip.contracts.materialize import import_workbook
    from nhdip.models import ColumnContract

    if s.execute(select(ColumnContract.id).limit(1)).first():
        # 결정 반영(추천안) — 연결이 이전 기본값 그대로인 컬럼만 새 기본값으로
        n = 0
        for c in s.execute(select(ColumnContract)).scalars():
            olds = DC.BINDING_UPGRADES.get(c.column_name)
            if olds and c.binding in olds and DC.BINDINGS.get(c.column_name) not in (None, c.binding):
                c.binding = DC.BINDINGS[c.column_name]
                n += 1
        out["contracts"] = {"exists": True, "binding_upgraded": n}
        if n:
            emit(s, "contract.changed", {"reason": "결정 반영(추천안)", "columns": n}, "seed")
        return
    with open(os.path.join(HERE, "contracts", "hq_column_def_v2.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    out["contracts"] = import_workbook(s, spec["tables"], spec["source_file"], DC.BINDINGS, "seed")


def _template_bindings() -> list[dict[str, Any]]:
    return [*D.bindings(), *B.bindings()]


def template_payload(key: str, payload: Any) -> Any:
    """화면 JSON → 값 없는 틀 (Phase I · Q138) — 시드 · 보강이 게시하는 0세대는 모두 이 틀이다."""
    from nhdip.views.template import to_template

    return to_template(key, payload, _template_bindings())


def seed_artifacts(s: Session, out: dict[str, Any]) -> None:
    if s.execute(select(func.count()).select_from(ViewArtifact)).scalar():
        out["artifacts"] = "exists"
        return
    n = 0
    fixes: dict[str, list[tuple[str, str]]] = {}
    for key, old, new in D.TEXT_FIXES:
        fixes.setdefault(key, []).append((old, new))
    for path in sorted(glob.glob(os.path.join(_screens_dir(), "*.json"))):
        key = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        for old, new in fixes.get(key, []):
            raw = raw.replace(json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(new, ensure_ascii=False)[1:-1])
        publish(s, key, template_payload(key, json.loads(raw)), produced_by="seed")
        n += 1
    out["artifacts"] = n


def fix_live_texts(s: Session, out: dict[str, Any]) -> None:
    """운영 DB 의 현재 산출물 문구 교정 — 옛 문구가 남아 있는 산출물만 새 세대로 게시."""
    from nhdip.views.store import get_current_row

    n = 0
    for (key,) in s.execute(select(ViewArtifact.key).where(ViewArtifact.is_current)).all():
        row = get_current_row(s, key)
        raw = json.dumps(row.payload, ensure_ascii=False)
        fixed = raw
        for old, new in D.LIVE_TEXT_FIXES:
            fixed = fixed.replace(json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(new, ensure_ascii=False)[1:-1])
        if fixed != raw:
            publish(s, key, json.loads(fixed), produced_by="seed-fix", changes=[{"text_fix": [o for o, _ in D.LIVE_TEXT_FIXES if json.dumps(o, ensure_ascii=False)[1:-1] in raw]}])
            s.flush()
            n += 1
    out["text_fixes"] = n


def fix_markers(s: Session, out: dict[str, Any]) -> None:
    """서술의 고정 숫자를 계산 수치 마커로 바꾸고, 그 인사이트에 수치(Figure)를 추가 — 1회 (PRIN-05)."""
    if _applied(s, "marker-fix-v1"):
        return
    from nhdip.views.store import get_current_row

    n = 0
    for fx in D.MARKER_FIXES:
        for key in fx["keys"]:
            row = get_current_row(s, key)
            if row is None:
                continue
            payload = json.loads(json.dumps(row.payload, ensure_ascii=False))
            touched = False
            stack = [payload]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    if o.get("id") in fx["id"]:
                        for f in fx["fields"]:
                            if isinstance(o.get(f), str):
                                new = o[f]
                                for a, b in fx["replace"]:
                                    new = new.replace(a, b)
                                if new != o[f]:
                                    o[f] = new
                                    figs = o.setdefault("figures", {})
                                    if isinstance(figs, dict):
                                        for fid, fig in fx["figures"].items():
                                            figs.setdefault(fid, dict(fig))
                                    touched = True
                    stack.extend(o.values())
                elif isinstance(o, list):
                    stack.extend(o)
            if touched:
                publish(s, key, payload, produced_by="seed-fix", changes=[{"marker_fix": fx["id"]}])
                s.flush()
                n += 1
    out["marker_fixes"] = n


def _psi_bands_upgrade(s: Session) -> None:
    """Q37 — PSI 임계가 이전 기본값 그대로일 때만 시나리오 판정과 맞는 잠정 임계로 새 버전."""
    if _applied(s, "psi-bands-v2"):
        return
    rule = s.get(Rule, "MDL_PSI_BANDS")
    if not rule:
        return
    cur = s.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
    if cur and cur.body == C.PSI_BANDS_V1:
        s.add(RuleVersion(rule_code=rule.code, version=rule.active_version + 1, body=C.PSI_BANDS_V2, note="Q37 추천안: 시나리오 판정과 일치하는 잠정 임계", created_by="seed"))
        rule.active_version += 1
        emit(s, "rule.changed", {"rule": rule.code, "version": rule.active_version}, "seed")


def _doc_head(doc: dict[str, Any]) -> list[str]:
    return [doc["title"], f"발행: {doc.get('issuer') or '-'} · 시행일 {doc.get('effectiveDate') or '-'} · 분류 {doc.get('dbClassLabel') or doc.get('dbClass')}", "주제어: " + ", ".join(doc.get("tags") or [])]


def _doc_text(doc: dict[str, Any], snippets: list[dict[str, Any]]) -> str:
    head = _doc_head(doc)
    body = []
    for sn in snippets:
        sec = sn.get("sectionPath") or ""
        body.append(f"{sec}\n{sn['snippet']}".strip())
    if not body:
        body.append(f"{doc['title']} — {', '.join(doc.get('tags') or [])} 관련 {doc.get('docType') or '문서'}.")
    return "\n\n".join(head + body)


def _collect_snippets() -> dict[str, list[dict[str, Any]]]:
    """화면 목데이터의 근거 인용(snippet)을 문서 제목별로 모은다."""
    snippets: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for path in sorted(glob.glob(os.path.join(_screens_dir(), "*.json"))):
        with open(path, encoding="utf-8") as fh:
            stack = [json.load(fh)]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if isinstance(o.get("doc"), dict) and o.get("snippet"):
                    title = o["doc"].get("title")
                    if (title, o["snippet"]) not in seen:
                        seen.add((title, o["snippet"]))
                        snippets.setdefault(title, []).append({"snippet": o["snippet"], "sectionPath": o["doc"].get("sectionPath"), "page": o["doc"].get("page")})
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return snippets


def _doc_pages(doc: dict[str, Any], snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """원본 파일이 없는 시드 문서의 면별 발췌 (F.12 뷰어) — 인용이 실린 면만, 면 번호 순."""
    by: dict[int, list[dict[str, Any]]] = {}
    for sn in snippets:
        by.setdefault(int(sn.get("page") or 1), []).append(sn)
    pages = []
    for page in sorted(by):
        items = by[page]
        sections = [x.get("sectionPath") for x in items if x.get("sectionPath")]
        text = "\n\n".join(f"{x.get('sectionPath') or ''}\n{x['snippet']}".strip() for x in items)
        pages.append({"page": page, "section": sections[0] if sections else None, "text": text})
    return pages


def upgrade_seed_documents(s: Session, out: dict[str, Any]) -> None:
    """운영 DB 의 시드 문서에 면별 발췌(meta.pages)가 없으면 추가 — 본문 · 청크는 그대로."""
    snippets = _collect_snippets()
    n = 0
    for origin in ("bank", "ext"):
        t = source(origin)
        for d in s.execute(select(t.document).where(t.document.is_current, t.document.uploaded_by == "seed")).scalars():
            meta = dict(d.meta or {})
            if meta.get("pages") or not snippets.get(d.title):
                continue
            meta["pages"] = _doc_pages(meta, snippets[d.title])
            d.meta = meta
            n += 1
    out["document_pages"] = n


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


def seed_documents(s: Session, out: dict[str, Any]) -> None:
    """시드는 문서를 넣지 않는다(Q135 — 문서는 업로드로). 예전 시드가 넣은 문서가 있는 DB 만 면별 발췌를 보강한다."""
    if s.execute(select(source("bank").document.id).limit(1)).first() or s.execute(select(source("ext").document.id).limit(1)).first():
        out["documents"] = "exists"
        upgrade_seed_documents(s, out)
        return
    out["documents"] = 0


def has_business_data(s: Session) -> bool:
    """확정된 데이터셋 버전이 하나라도 있는지 — 없으면(정의만 있는 새 DB) 선계산을 걸지 않는다."""
    return any(s.execute(select(source(o).version.id).where(source(o).version.is_current).limit(1)).first() for o in ("bank", "ext"))


def branch_upgrade(s: Session, out: dict[str, Any], first: bool) -> None:
    """영업점 시나리오(B.29) 운영 DB 보강 — 1회. 새 DB 는 각 시드 단계가 이미 채우므로 비어 있는 것만 넣는다(관리자 편집 보존)."""
    if _applied(s, "branch-v1"):
        return
    done: dict[str, Any] = {}
    # 화면: 영업점 홈은 현황(대시보드)으로 — 이전 기본값 그대로일 때만
    home = s.get(Screen, "BRANCH_HOME")
    if home and home.label == "내 목표·가이드":
        spec = next(x for x in C.SCREENS if x["code"] == "BRANCH_HOME")
        home.label, home.match, home.step = spec["label"], spec.get("match"), spec.get("step")
        done["screen_home"] = True
    # 화면 리소스 · 질의 리소스 · 문서 분류 — 없는 키만 합친다
    res = s.get(Setting, "screen.resources")
    if res is not None:
        cur = dict(res.value or {})
        for sc in C.SCREENS:
            if sc["code"].startswith("BRANCH_"):
                have = list(cur.get(sc["code"]) or [])
                cur[sc["code"]] = have + [r for r in sc.get("resources", []) if r not in have]
        res.value = cur
    for key in ("assist.workflow_resources", "doc_class.labels", "doc_class.default_origin"):
        st = s.get(Setting, key)
        if st is not None and isinstance(st.value, dict):
            st.value = {**C.SETTINGS[key][0], **st.value}
    bl = s.get(Setting, "ui.batch_label")
    if bl is not None and "wf_branch_kpi" not in str(bl.value) and str(bl.value).startswith("변경 기반 실행 ("):
        bl.value = C.SETTINGS["ui.batch_label"][0]
    # 표 · 차트 바인딩 (바인딩 시드는 빈 테이블에서만 돌므로)
    if not s.execute(select(ViewBinding).where(ViewBinding.workflow_code == B.WF)).first():
        for b in B.bindings():
            s.add(ViewBinding(**b, enabled=True))
        done["bindings"] = len(B.bindings())
    # 화면 산출물 — 없는 키만 게시
    n = 0
    for key in B.ARTIFACT_KEYS:
        path = os.path.join(_screens_dir(), f"{key}.json")
        if os.path.exists(path) and not s.execute(select(ViewArtifact.id).where(ViewArtifact.key == key).limit(1)).first():
            with open(path, encoding="utf-8") as fh:
                publish(s, key, template_payload(key, json.load(fh)), produced_by="seed")
            n += 1
    done["artifacts"] = n
    # 문서 — 영업점 기준 · 공문: 예전 시드 문서가 있던 운영 DB 만(없는 문서만). 새 DB 는 업로드로(Q135)
    from nhdip.sample.docs import catalog

    docs = {d["docId"]: d for d in catalog()}
    have_docs = {c for o in ("bank", "ext") for c in s.execute(select(source(o).document.doc_code)).scalars()}
    snippets = _collect_snippets()
    nd = 0
    for doc_id in B.DOC_IDS if (not first and have_docs) else []:
        d = docs.get(doc_id)
        if not d or doc_id in have_docs:
            continue
        pages = _doc_pages(d, snippets.get(d["title"], []))
        ingest_document(s, origin="ext" if d["dbClass"] == "gov_policy" else "bank", doc_code=doc_id, title=d["title"], doc_class=d["dbClass"], text=_doc_text(d, snippets.get(d["title"], [])),
                        pages=[(p["page"], ("\n".join(_doc_head(d)) + "\n\n" + p["text"]) if i == 0 else p["text"]) for i, p in enumerate(pages)] or None,
                        issuer=d.get("issuer"), published_at=d.get("effectiveDate"), meta={**d, "pages": pages} if pages else d, actor="seed", emit_event=False)
        nd += 1
    done["documents"] = nd
    s.flush()
    if not first:
        for wf in ("wf_graph_projection", B.WF):
            emit(s, "manual", {"workflow": wf, "reason": "영업점 시나리오 보강 후 계산"}, "seed")
    out["branch_upgrade"] = done


def agents_upgrade(s: Session, out: dict[str, Any]) -> None:
    """판단 에이전트(B.30) 운영 DB 보강 — 1회. 업무 화면에 변화 피드 리소스(changes)를 더한다(관리자 편집 보존)."""
    if _applied(s, "agents-v1"):
        return
    res = s.get(Setting, "screen.resources")
    if res is not None:
        cur = dict(res.value or {})
        for sc in C.SCREENS:
            if "changes" in sc.get("resources", []):
                have = list(cur.get(sc["code"]) or [])
                if "changes" not in have:
                    cur[sc["code"]] = have + ["changes"]
        res.value = cur
    out["agents_upgrade"] = True



def agents_llm_upgrade(s: Session, out: dict[str, Any]) -> None:
    """판단 에이전트 LLM 전환(B.31) — 1회. 규칙형으로 만들어진 에이전트를 LLM 형으로(프롬프트 v1), 규칙 · 설정에 새 키만 추가."""
    if _applied(s, "agents-llm-v1"):
        return
    default = s.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars().first()
    done = []
    for code, name, role, kind, profile, system in C.AGENTS:
        if code not in ("change_detector", "planner", "orchestrator"):
            continue
        a = s.get(Agent, code)
        if a is None or a.kind != "rule":
            continue
        a.kind, a.role = kind, role
        if default is not None and a.profile_id is None:
            a.profile_id = default.id
        if not s.execute(select(Prompt).where(Prompt.agent_code == code)).first():
            s.add(Prompt(agent_code=code, version=1, system=system, user_template="", note="B.31 LLM 판단 전환 초기 프롬프트", created_by="seed"))
        done.append(code)
    # 규칙 · 설정 — 없는 키만 새 버전으로 (관리자 값 보존)
    for code in ("CHANGE_SIGNIFICANCE", "PLANNER_POLICY"):
        rule = s.get(Rule, code)
        spec = next((r for r in C.RULES if r[0] == code), None)
        if rule is None or spec is None:
            continue
        cur = s.execute(select(RuleVersion).where(RuleVersion.rule_code == code, RuleVersion.version == rule.active_version)).scalar()
        body = dict(cur.body) if cur else {}
        missing = {k: v for k, v in spec[4].items() if k not in body}
        if missing:
            last = s.execute(select(RuleVersion.version).where(RuleVersion.rule_code == code).order_by(RuleVersion.version.desc()).limit(1)).scalar() or 0
            s.add(RuleVersion(rule_code=code, version=last + 1, body={**body, **missing}, note=f"B.31 LLM 판단 키 추가: {', '.join(missing)}", created_by="seed"))
            rule.active_version, rule.name = last + 1, spec[1]
    for key in ("orchestrator.policy",):
        st = s.get(Setting, key)
        if st is not None and isinstance(st.value, dict):
            st.value = {**C.SETTINGS[key][0], **st.value}
    # 영업점 알림의 배점표 항목 코드(itemCode) — 시드 산출물 기준으로 비어 있는 키만 채운다
    from nhdip.views.store import get_current_row

    row = get_current_row(s, "branch_dashboard")
    path = os.path.join(_screens_dir(), "branch_dashboard.json")
    if row is not None and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            seed_alerts = {a["id"]: a for a in json.load(fh).get("alerts", [])}
        payload = copy.deepcopy(row.payload)
        changed = False
        for a in payload.get("alerts") or []:
            if "itemCode" not in a and seed_alerts.get(a.get("id"), {}).get("itemCode"):
                a["itemCode"] = seed_alerts[a["id"]]["itemCode"]
                changed = True
        if changed:
            publish(s, "branch_dashboard", payload, produced_by="seed-fix", changes=[{"added": "alerts.itemCode"}])
    sc = s.get(Screen, "RISK_ANALYSIS")
    if sc is not None and sc.path == "/risk/analysis/model-monitoring":
        sc.path = "/risk/analysis"  # 첫 번째 분석 탭으로 이동하는 진입 경로 (탭 키를 메뉴에 두지 않는다)
    out["agents_llm_upgrade"] = done


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


def dept_contracts_upgrade(s: Session, out: dict[str, Any], first: bool) -> None:
    """사업부서 · 영업점 컬럼 정의서(B.38) — 1회. 정의서 반영 · 부서 접두 · 행 생성기 설정 · 적재 노드(관리자 편집 보존: 없는 것만 넣는다)."""
    from nhdip.contracts.materialize import import_workbook
    from nhdip.models import ColumnContract, WorkflowNode
    from nhdip.seed import defs_dept_contracts as DD

    up = 0
    for key, olds in DD.BINDING_UPGRADES.items():
        t, col = key.split(".", 1)
        c = s.execute(select(ColumnContract).where(ColumnContract.table_code == t, ColumnContract.column_name == col)).scalar()
        if c is not None and c.binding in olds and c.binding != DD.BINDINGS.get(key):
            c.binding = DD.BINDINGS[key]
            up += 1
    if up:
        out["dept_binding_upgraded"] = up
    if _applied(s, "dept-contracts-v1"):
        return
    done: dict[str, Any] = {}
    st = s.get(Setting, "contracts.dept_prefix")
    if st is not None and isinstance(st.value, dict):
        st.value = {**DD.DEPT_PREFIX, **st.value}
    else:
        s.add(Setting(key="contracts.dept_prefix", value={"종기부": "hq", "리스크": "risk", "영업점": "branch", **DD.DEPT_PREFIX}, description="정의서 부서 → mart 테이블 접두"))
    if s.get(Setting, "contracts.row_builders") is None:
        s.add(Setting(key="contracts.row_builders", value=DD.ROW_BUILDERS,
                      description="다행 정의서 표의 행 생성기(contracts/rows.py) · 파라미터 — 표 코드 → {builder, params}. 단위 환산 계수는 데이터셋 정의 단위 기준"))
    s.flush()
    for fn in DD.SPEC_FILES:
        with open(os.path.join(HERE, "contracts", fn), encoding="utf-8") as fh:
            spec = json.load(fh)
        new = [t for t in spec["tables"] if not s.execute(select(ColumnContract.id).where(ColumnContract.table_code == t["table_code"]).limit(1)).first()]
        if new:
            done[fn] = import_workbook(s, new, spec["source_file"], DD.BINDINGS, "seed")
    nodes = 0
    for wf, tables in DD.WORKFLOW_TABLES.items():
        have = s.execute(select(WorkflowNode).where(WorkflowNode.workflow_code == wf).order_by(WorkflowNode.seq)).scalars().all()
        if not have or any(n.key == "contracts" for n in have):
            continue
        pub = next((n for n in have if n.impl == "publish"), None)
        seq = pub.seq if pub else max(n.seq for n in have) + 1
        if pub:
            for n in have:
                if n.seq >= seq:
                    n.seq += 1
        s.add(WorkflowNode(workflow_code=wf, seq=seq, key="contracts", name="컬럼 정의서 테이블 적재·대조", impl="materialize_contracts", enabled=True, config={"tables": tables, "optional": True}))
        nodes += 1
    done["nodes"] = nodes
    s.flush()
    if not first:
        for wf in DD.WORKFLOW_TABLES:
            emit(s, "manual", {"workflow": wf, "reason": "사업부서 · 영업점 컬럼 정의서 반영 후 적재"}, "seed")
    out["dept_contracts_upgrade"] = done


def score_snapshot_upgrade(s: Session, out: dict[str, Any]) -> None:
    """B.40 — 득점 현황(BRANCH_KPI_SCORE)은 기준일 스냅숏: 새 기준일을 올리면 이전 기준일 행과 중복 합산되던 지표에 '최근 기준일' 조건을 더한다(조건이 없을 때만 · 멱등)."""
    from nhdip.models import Metric

    n = 0
    for m in s.execute(select(Metric)).scalars():
        args = json.loads(json.dumps(m.args or {}))
        hit = False
        for ref in args.values():
            q = ref.get("q") if isinstance(ref, dict) else None
            if isinstance(q, dict) and q.get("dataset") == "BRANCH_KPI_SCORE" and "as_of" not in (q.get("where") or {}):
                q["where"] = {**(q.get("where") or {}), "as_of": "$latest"}
                hit = True
        if hit:
            m.args = args
            n += 1
    # 마케팅 후보 '미거래' 조건 — 지표 br_prospect_pick 에 기존 차주 입력이 없으면 추가 (B.40 · 관리자가 지운 경우를 구분하려고 1회)
    if not _applied(s, "prospect-existing-v1"):
        m = s.get(Metric, "br_prospect_pick")
        if m is not None and m.formula == "PROSPECT_SELECT" and "existing" not in (m.args or {}):
            m.args = {**(m.args or {}), "existing": B.PROSPECT_EXISTING}
            n += 1
    if n:
        out["score_snapshot_upgrade"] = n


def merge_aliases(cur: dict[str, Any] | None, add: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """별칭 사전에 없는 별칭만 더한다 — 관리자가 넣은 키 · 별칭은 그대로, 지운 키는 되살리지 않는다(키가 남아 있을 때만 보강)."""
    out = copy.deepcopy(cur or {})
    n = 0
    for label, entries in add.items():
        have_label = out.get(label)
        if not isinstance(have_label, dict):
            continue
        for key, aliases in entries.items():
            if key not in have_label:
                continue
            have = list(have_label.get(key) or [])
            new = [a for a in aliases if a not in have]
            if new:
                have_label[key] = have + new
                n += len(new)
    return out, n


def ontology_extraction_upgrade(s: Session, out: dict[str, Any]) -> None:
    """B.42 — 온톨로지 추출 '부분 추출' 보완, 1회. ① 추출 프롬프트가 초기값 그대로면 새 버전(근거 복사 · 마스터 키 우선)
    ② 활성 스키마 별칭 사전에 없는 별칭만 더한 새 스키마 버전(관리자 편집 보존). 되돌리기: 관리자 [에이전트] 프롬프트 · [온톨로지] 스키마 버전."""
    if _applied(s, "ontology-extraction-v2"):
        return
    done: dict[str, Any] = {}
    a = s.get(Agent, "ontology_extractor")
    if a is not None and a.prompt_version is None:
        last = s.execute(select(Prompt).where(Prompt.agent_code == a.code).order_by(Prompt.version.desc()).limit(1)).scalar()
        if last is not None and last.system == C.EXTRACTOR_SYSTEM_V1 and not (last.user_template or "").strip():
            s.add(Prompt(agent_code=a.code, version=last.version + 1, system=C.EXTRACTOR_SYSTEM, user_template="", note="B.42 근거 문장 복사 · 마스터 키 우선 (초기 프롬프트였던 경우만)", created_by="seed"))
            done["prompt"] = last.version + 1
    sc = s.execute(select(OntologySchema).where(OntologySchema.active).order_by(OntologySchema.version.desc()).limit(1)).scalar()
    if sc is not None:
        merged, n = merge_aliases(sc.aliases, C.ONTOLOGY_ALIASES)
        if n:
            last_v = s.execute(select(func.max(OntologySchema.version))).scalar() or sc.version
            sc.active = False
            s.add(OntologySchema(version=last_v + 1, classes=sc.classes, relations=sc.relations, aliases=merged, active=True, note=f"B.42 별칭 보강 +{n} (v{sc.version} 기준, 관리자 편집 보존)"))
            done["aliases_added"] = n
    if done:
        out["ontology_extraction_upgrade"] = done


# 이전 관리자 메뉴 기본값(묶음 · 이름) — 관리자가 바꾸지 않은 화면만 새 묶음으로 옮긴다 (Phase C · Q104)
_OLD_ADMIN_SECTIONS = {"관리자", "관리자 · 모니터링"}
_OLD_ADMIN_LABELS = {"ADMIN_HOME": "시스템 상태", "ADMIN_AGENTS": "에이전트", "ADMIN_WORKFLOWS": "워크플로우"}


def admin_ia_upgrade(s: Session, out: dict[str, Any]) -> None:
    """관리자 정보 구조(Phase C · ADM-01) — 1회. 관리자 화면을 묶음 6개로(이전 기본 묶음인 화면만), 이전 기본 이름만 새 이름으로.
    새 화면(운영 개요 · 운영 설정 등)은 seed_iam 이 없을 때 추가한다. 되돌리기: 관리자 [화면 권한]에서 묶음 · 이름 편집."""
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


def assist_rename_upgrade(s: Session, out: dict[str, Any]) -> None:
    """화면 이름 '질문하기' → 'AI 어시스턴트' — 1회. 관리자 메뉴의 이전 기본 이름('질문하기 색인')인 화면만 새 이름으로(관리자가 바꾼 이름은 보존)."""
    if _applied(s, "assist-rename-v1"):
        return
    sc = s.get(Screen, "ADMIN_KNOWLEDGE")
    if sc is not None and sc.label == "질문하기 색인":
        sc.label = "AI 어시스턴트 색인"
        out["assist_rename_upgrade"] = 1


def search_3way_upgrade(s: Session, out: dict[str, Any]) -> None:
    """3-way 검색 구성(Phase H · 설계 §24) — 1회. 검색 설정 knowledge.search.backend 가 예전 기본값 'pg' 이면 'auto' 로
    (ES_URL 이 있으면 Elasticsearch, 없으면 지금처럼 PostgreSQL). 관리자가 이후 'pg' 로 되돌리면 다시 바꾸지 않는다."""
    if _applied(s, "search-3way-v1"):
        return
    st = s.get(Setting, "knowledge.search")
    if st is not None and isinstance(st.value, dict) and str(st.value.get("backend", "pg")).strip().lower() == "pg":
        st.value = {**st.value, "backend": "auto"}
        out["search_3way_upgrade"] = 1


def _merge_screen_resources(s: Session, codes: set[str]) -> list[str]:
    """새 화면의 리소스를 설정 screen.resources 에 더한다 — 그 화면 키가 없을 때만(관리자 편집 보존)."""
    res = s.get(Setting, "screen.resources")
    if res is None:
        return []
    cur = dict(res.value or {})
    added = []
    for sc in C.SCREENS:
        if sc["code"] in codes and sc.get("resources") and sc["code"] not in cur:
            cur[sc["code"]] = list(sc["resources"])
            added.append(sc["code"])
    res.value = cur
    return added


def upload_request_upgrade(s: Session, out: dict[str, Any]) -> None:
    """업무 자료 올리기(Phase C · UPL) — 1회. 새 화면(자료 올리기)의 리소스 db_upload 를 화면 리소스 설정에 더한다.
    화면 · 기본 권한(종합기획부 · 신용리스크관리부)은 seed_iam 이 없을 때 추가. 되돌리기: 관리자 [화면 권한]에서 회수."""
    if _applied(s, "upload-request-v1"):
        return
    out["upload_request_upgrade"] = _merge_screen_resources(s, {"KNOWLEDGE_UPLOAD"})


def _add_screen_resources(s: Session, code: str, resources: list[str]) -> list[str]:
    """기존 화면의 리소스 목록에 새 리소스를 더한다(없는 것만 · 관리자 편집 보존)."""
    res = s.get(Setting, "screen.resources")
    if res is None:
        return []
    cur = dict(res.value or {})
    have = list(cur.get(code) or [])
    add = [r for r in resources if r not in have]
    if add and code in cur:
        cur[code] = have + add
        res.value = cur
    return add if code in cur else []


def analysis_spaces_upgrade(s: Session, out: dict[str, Any]) -> None:
    """분석 레지스트리(Phase C · DAG-07) — 1회. (v2 · Q109) 새 분석은 기존 부서 분석 화면의 탭으로 — 종합기획부 [데이터 분석]이 맞춤 분석 탭을 보도록 리소스 hq_reports 를 더하고,
    v1 에서 만든 별도 메뉴 [분석 보고서](ANALYSIS_HQ)는 끈다(/analysis/hq 주소는 /hq/analysis 로 이동)."""
    if _applied(s, "analysis-spaces-v2"):
        return
    done: dict[str, Any] = {"HQ_ANALYSIS": _add_screen_resources(s, "HQ_ANALYSIS", ["hq_reports"])}
    old = s.get(Screen, "ANALYSIS_HQ")
    if old is not None and old.active:
        old.active = False
        done["ANALYSIS_HQ"] = "inactive"
    out["analysis_spaces_upgrade"] = done


def analysis_agents_upgrade(s: Session, out: dict[str, Any]) -> None:
    """분석 에이전트(Phase C · DAG) — 1회. 분석 만들기 화면의 리소스 analysis_builder 를 더한다(정제 · 렌더링 에이전트는 seed_cfg 가 없을 때 추가)."""
    if _applied(s, "analysis-agents-v1"):
        return
    out["analysis_agents_upgrade"] = _merge_screen_resources(s, {"ANALYSIS_BUILDER"})


def admin_counts_upgrade(s: Session, out: dict[str, Any]) -> None:
    """관리자 처리 대기 건수(Phase E · NAV-04 · Q122) — 1회. 관리자 홈 · 사용자 · 자료 승인 · 분석 에이전트 화면에 건수 키를 단다.
    관리자가 건수 키를 이미 지정한 화면은 건드리지 않는다. 되돌리기: 관리자 [화면 권한]에서 건수 키를 비운다."""
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


def _add_missing(cur: Any, seed: Any) -> Any:
    """규칙 본문 보강 — 관리자가 바꾼 값은 두고, 새로 정의된 키만 더한다(중첩 사전까지)."""
    if not isinstance(cur, dict) or not isinstance(seed, dict):
        return cur
    out = dict(cur)
    for k, v in seed.items():
        out[k] = _add_missing(cur[k], v) if k in cur else v
    return out


PHASE_I_RULES = ("MDL_AR_BASELINE", "PROPOSAL_IMPACT")


def phase_i_upgrade(s: Session, out: dict[str, Any], first: bool) -> None:
    """Phase I (Q135~Q142) — 운영 DB 보강(1회). 새 DB 는 정의가 이미 최신이라 표시만 남긴다.
    - 지표: 정의에 새로 생긴 수치 id(figure_ids)를 더한다(기존 id · 산식은 그대로)
    - 화면 바인딩: (워크플로우, 산출물, 경로) 가 없는 것만 더한다
    - 규칙: MDL_AR_BASELINE(모형 5개 추가) · PROPOSAL_IMPACT(hh_rwa_factor) — 없는 키만 더해 새 버전
    - 설정 ui.as_of: 예전 고정값(2026-08-31)이면 비운다(올라온 자료의 최신 기준일)"""
    if _applied(s, "phase-i-v1") or first:
        return
    n_fig = 0
    for m in [*D.metrics(), *DC.metrics(), *B.metrics()]:
        cur = s.get(Metric, m["code"])
        if cur is None:
            continue
        want = [f for f in (m.get("figure_ids") or []) if f not in (cur.figure_ids or [])]
        if want:
            cur.figure_ids = [*(cur.figure_ids or []), *want]
            n_fig += len(want)
    have = {(b.workflow_code, b.artifact_key, b.path) for b in s.execute(select(ViewBinding)).scalars()}
    n_bind = 0
    for b in _template_bindings():
        if (b["workflow_code"], b["artifact_key"], b["path"]) not in have:
            s.add(ViewBinding(**b, enabled=True))
            have.add((b["workflow_code"], b["artifact_key"], b["path"]))
            n_bind += 1
    n_rule = 0
    seeds = {code: body for code, _n, _k, _d, body in [*C.RULES, DC.RULE, DC.RULE_IMPACT, *B.RULES, *R.RULES]}
    for code in PHASE_I_RULES:
        rule = s.get(Rule, code)
        if rule is None or code not in seeds:
            continue
        cur = s.execute(select(RuleVersion).where(RuleVersion.rule_code == code, RuleVersion.version == rule.active_version)).scalar()
        if cur is None:
            continue
        merged = _add_missing(cur.body, seeds[code])
        if merged != cur.body:
            last = s.execute(select(func.max(RuleVersion.version)).where(RuleVersion.rule_code == code)).scalar() or rule.active_version
            s.add(RuleVersion(rule_code=code, version=last + 1, body=merged, note="Phase I: 새 키 추가(기존 값 유지)", created_by="seed"))
            rule.active_version = last + 1
            emit(s, "rule.changed", {"rule": code, "version": last + 1}, "seed")
            n_rule += 1
    st = s.get(Setting, "ui.as_of")
    as_of_cleared = bool(st and st.value == "2026-08-31")
    if as_of_cleared:
        st.value = ""
    s.flush()
    out["phase_i"] = {"figure_ids": n_fig, "bindings": n_bind, "rules": n_rule, "ui_as_of_cleared": as_of_cleared}


def data_admin_upgrade(s: Session, out: dict[str, Any]) -> None:
    """Phase J (DEL-01 · Q143) — 운영 DB 에 데이터 관리자가 한 명도 없으면 부트스트랩 관리자를 지정(1회). 이후 지정 · 해제는 [사용자] 화면."""
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
    """질문하기 통합 지식 색인(Phase D · 요구사항 §21) — 컬렉션 정의(없는 코드만, 관리자 편집 보존) + 분석 결과 색인 대조.
    새 DB · 업그레이드 · 직접 게시 경로를 모두 보강한다(멱등 — 이미 색인된 것은 건드리지 않음). 임베딩은 워커가 채운다."""
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


def run_seed(s: Session, with_precompute: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    first = not s.execute(select(func.count()).select_from(Workflow)).scalar()
    seed_iam(s, out)
    seed_cfg(s, out)
    s.flush()
    seed_artifacts(s, out)
    s.flush()  # 새로 게시한 산출물에도 문구 교정이 보이도록 (autoflush 꺼짐)
    if not first:  # 예전 시드 문구가 남은 운영 DB 만 — 새 DB 의 틀은 이미 수치 마커 · 서식 문구(Phase I)
        fix_live_texts(s, out)
        fix_markers(s, out)
    seed_documents(s, out)
    s.flush()
    backfill_section_paths(s, out)
    seed_contracts(s, out)
    s.flush()
    branch_upgrade(s, out, first)
    agents_upgrade(s, out)
    agents_llm_upgrade(s, out)
    hardening_upgrade(s, out)
    s.flush()
    dept_contracts_upgrade(s, out, first)
    score_snapshot_upgrade(s, out)
    ontology_extraction_upgrade(s, out)
    admin_ia_upgrade(s, out)
    assist_rename_upgrade(s, out)
    upload_request_upgrade(s, out)
    analysis_spaces_upgrade(s, out)
    analysis_agents_upgrade(s, out)
    admin_counts_upgrade(s, out)
    phase_i_upgrade(s, out, first)
    data_admin_upgrade(s, out)
    s.flush()
    seed_knowledge(s, out)
    s.flush()
    search_3way_upgrade(s, out)
    s.flush()
    # 시드로 생긴 dataset.committed 이벤트는 그대로 두면 관련 워크플로우가 모두 돈다.
    # 최초 시드 + precompute 요청 시: 그래프 투영을 먼저, 이후 업무 워크플로우를 즉시 실행하도록 수동 이벤트를 추가.
    if first and with_precompute and has_business_data(s):
        from nhdip.models import OutboxEvent

        s.query(OutboxEvent).filter(OutboxEvent.dispatched_at.is_(None)).update({"dispatched_at": func.now(), "matched": [{"note": "seed — 수동 실행 이벤트로 대체"}]}, synchronize_session=False)
        for wf in ("wf_graph_projection", "wf_model_monitoring", "wf_inclusive_risk", "wf_hq_goal_review", B.WF):
            emit(s, "manual", {"workflow": wf, "reason": "최초 시드 후 계산"}, "seed")
        out["precompute"] = "queued"
    s.commit()
    return out
