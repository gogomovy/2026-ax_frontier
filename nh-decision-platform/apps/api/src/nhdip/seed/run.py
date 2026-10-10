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
from nhdip.data.datasets import ingest_rows, quality_check
from nhdip.data.documents import ingest_document
from nhdip.events import audit, emit
from nhdip.models import (
    Agent,
    AppUser,
    Dataset,
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
        s.add(AppUser(emp_no=st.bootstrap_admin_emp_no, name="시스템 관리자", password_hash=hash_password(st.bootstrap_admin_password), org_code="T911", position="관리자", role="admin", status="active", approved_by="bootstrap"))
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
    for code, name, kind, desc, body in [*C.RULES, DC.RULE, DC.RULE_IMPACT, *B.RULES]:
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
        conn = LlmConnection(name="litellm", base_url=st.llm_default_base_url, api_key_enc=encrypt_secret(st.llm_default_api_key), active=True, note="docker compose 의 LiteLLM 게이트웨이. 키는 LiteLLM 가상 키 또는 마스터 키")
        s.add(conn)
        s.flush()
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
        publish(s, key, json.loads(raw), produced_by="seed")
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
    if s.execute(select(source("bank").document.id).limit(1)).first() or s.execute(select(source("ext").document.id).limit(1)).first():
        out["documents"] = "exists"
        upgrade_seed_documents(s, out)
        return
    with open(os.path.join(_screens_dir(), "documents.json"), encoding="utf-8") as fh:
        docs = json.load(fh)
    snippets = _collect_snippets()
    n = 0
    for d in docs:
        origin = "ext" if d["dbClass"] == "gov_policy" else "bank"
        doc_snips = snippets.get(d["title"], [])
        pages = _doc_pages(d, doc_snips)
        ingest_document(
            s,
            origin=origin,
            doc_code=d["docId"],
            title=d["title"],
            doc_class=d["dbClass"],
            text=_doc_text(d, doc_snips),
            # 청크: 첫 면에 문서 머리글(제목 · 발행 · 주제어)을 붙여 검색에 쓰이게 한다
            pages=[(p["page"], ("\n".join(_doc_head(d)) + "\n\n" + p["text"]) if i == 0 else p["text"]) for i, p in enumerate(pages)] or None,
            issuer=d.get("issuer"),
            published_at=d.get("effectiveDate"),
            meta={**d, "pages": pages} if pages else d,
            actor="seed",
            emit_event=False,
        )
        n += 1
    out["documents"] = n


def seed_datasets(s: Session, out: dict[str, Any]) -> None:
    n = 0
    for spec in [*D.dataset_versions(), DC.dataset_version(), *B.dataset_versions()]:
        ds = s.get(Dataset, spec["dataset"])
        t = source(ds.origin)
        exists = s.execute(select(t.version.id).where(t.version.dataset_code == ds.code, t.version.file_name == spec["file_name"]).limit(1)).first()
        if exists:
            continue
        rows = [dict(r) for r in spec["rows"]]
        # 정의에 없는 키는 버리고 누락 키는 None
        names = [c["name"] for c in ds.columns]
        rows = [{k: r.get(k) for k in names} for r in rows]
        quality = quality_check(ds, rows, [])
        ingest_rows(s, ds, rows, quality=quality, file_name=spec["file_name"], data_origin="simulated", actor="seed", note="목데이터 시뮬레이션 버전", force=True)
        n += 1
    out["dataset_versions"] = n


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
                publish(s, key, json.load(fh), produced_by="seed")
            n += 1
    done["artifacts"] = n
    # 문서 — 영업점 기준 · 공문 (없는 문서만)
    with open(os.path.join(_screens_dir(), "documents.json"), encoding="utf-8") as fh:
        docs = {d["docId"]: d for d in json.load(fh)}
    have_docs = {c for o in ("bank", "ext") for c in s.execute(select(source(o).document.doc_code)).scalars()}
    snippets = _collect_snippets()
    nd = 0
    for doc_id in B.DOC_IDS:
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


def run_seed(s: Session, with_precompute: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    first = not s.execute(select(func.count()).select_from(Workflow)).scalar()
    seed_iam(s, out)
    seed_cfg(s, out)
    s.flush()
    seed_artifacts(s, out)
    s.flush()  # 새로 게시한 산출물에도 문구 교정이 보이도록 (autoflush 꺼짐)
    fix_live_texts(s, out)
    fix_markers(s, out)
    seed_documents(s, out)
    s.flush()
    backfill_section_paths(s, out)
    seed_datasets(s, out)
    seed_contracts(s, out)
    s.flush()
    branch_upgrade(s, out, first)
    agents_upgrade(s, out)
    s.flush()
    # 시드로 생긴 dataset.committed 이벤트는 그대로 두면 관련 워크플로우가 모두 돈다.
    # 최초 시드 + precompute 요청 시: 그래프 투영을 먼저, 이후 업무 워크플로우를 즉시 실행하도록 수동 이벤트를 추가.
    if first and with_precompute:
        from nhdip.models import OutboxEvent

        s.query(OutboxEvent).filter(OutboxEvent.dispatched_at.is_(None)).update({"dispatched_at": func.now(), "matched": [{"note": "seed — 수동 실행 이벤트로 대체"}]}, synchronize_session=False)
        for wf in ("wf_graph_projection", "wf_model_monitoring", "wf_inclusive_risk", "wf_hq_goal_review", B.WF):
            emit(s, "manual", {"workflow": wf, "reason": "최초 시드 후 계산"}, "seed")
        out["precompute"] = "queued"
    s.commit()
    return out
