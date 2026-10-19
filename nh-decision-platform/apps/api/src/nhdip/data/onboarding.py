"""팀별 자료 등록(온보딩) — 정형 · 비정형 자료 분석 → 확인 · 반영 → 반영 상태 (Phase M · 요구사항 §31 DOB-01~06 · Q191~Q197)

  analyze_upload     파일 → 정형(엑셀 · CSV · JSON) / 비정형(PDF · 워드 · 텍스트) 판별
    정형   기존 정의와 맞추기(파일 이름 규칙 · 머리글 겹침) → 기존 자료면 그 정의로 같은 품질 검사 미리보기,
           새 자료면 정의 추론(DEF-01) + 구조 파악(ONB-04) + 정형 자료 등록 에이전트(data_intake — 이름 · 설명 · 열 업무 이름 · 의미)
    비정형 본문 읽기 → 규칙(파일 이름 · 첫 머리 · 분류 키워드 · 날짜 · 기관) + 문서 등록 에이전트(doc_intake — 제목 · 분류 · 기관 · 시행일 · 출처 · 요약)
  storage_status     반영된 등록 건의 단계별 상태 — 원장 · 임베딩 · Elasticsearch · 그래프 · 온톨로지 구축 · 이어진 워크플로

반영 자체는 기존 확정 경로(`api.db_uploads.do_approve` → ingest_file · ingest_document)를 그대로 쓴다 — 소유(Q157) · 감사 · 품질 검사 · 이벤트가 같다.
LLM 은 이름 · 의미 · 분류만 정하고(값 예시는 가림), 없거나 실패하면 규칙 결과로 끝까지 간다(Q193).
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, Setting

STRUCTURED_EXT = (".csv", ".xlsx", ".json")
DATE_RE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
ISSUERS = ("금융위원회", "금융감독원", "한국은행", "기획재정부", "예금보험공사", "신용보증기금", "서민금융진흥원", "농협중앙회", "NH농협은행", "농협금융지주", "금융결제원", "국토교통부")


def is_structured(filename: str, content: bytes | None = None) -> bool:
    """정형 자료인가 — 표 파일 확장자, 또는 표(파이프 표)가 든 마크다운(.md · Phase Q MD-03). 표가 없는 .md 는 문서."""
    name = (filename or "").lower()
    if name.endswith(STRUCTURED_EXT):
        return True
    if name.endswith((".md", ".markdown")) and content is not None:
        from .mdtable import is_md_table

        return is_md_table(content)
    return False


# ═════════════════════════ 정형 ═════════════════════════
def match_datasets(session: Session, filename: str, headers: list[str]) -> list[dict[str, Any]]:
    """기존 정의 후보 — 파일 이름 규칙(0.6) + 머리글 겹침(정의 열의 이름 · 라벨 · 별칭 대비 최대 0.4). 점수 높은 순 3개."""
    from .datasets import _norm, header_candidates

    from .sources import Resolver

    res = Resolver(session)
    hs = {_norm(h) for h in headers if h}
    out = []
    for d in session.execute(select(Dataset).where(Dataset.active)).scalars():
        score, why = 0.0, []
        if d.file_pattern:
            try:
                if re.search(d.file_pattern, filename or ""):
                    score += 0.6
                    why.append("파일 이름 규칙 일치")
            except re.error:
                pass
        cands = header_candidates(d)
        if cands and hs:
            hit = len(hs & cands)
            need = max(1, len([c for c in d.columns or [] if c.get("required")]) or len(d.columns or []))
            ratio = min(1.0, hit / need)
            if hit:
                score += 0.4 * ratio
                why.append(f"머리글 {hit}개 일치")
            # 열 구성이 거의 같으면(양쪽 90% 이상) 같은 자료 — 파일 이름이 달라도(예: 기준분포 · 모니터링 집계) 새 자료를 만들지 않게 (M.25)
            names = {_norm(c.get("name")) for c in d.columns or []} | {_norm(c.get("label")) for c in d.columns or [] if c.get("label")}
            own = {h for h in hs if h in names}
            if d.columns and len(own) >= 0.9 * len(hs) and len(own) >= 0.9 * len(d.columns):
                score += 0.3
                why.append("열 구성이 같음")
        if score > 0:
            # 업무 구성이 찾는 자료 모양(필요한 열)을 이 파일은 갖췄는데 이 정의는 못 갖췄다 — 여기 넣으면 업무 화면이 자료를 못 읽는다(예전 시드 정의 등).
            # 자동 연결 점수 밑으로 내려 새 정의를 만들게 한다(후보 목록에는 남겨 사람이 고를 수는 있게)
            sp = res.breaks_spec(d, headers)
            if sp is not None:
                score = min(score, 0.3)
                why.append(f"업무 구성 자료 '{sp.name}' 모양과 다름 — 새 정의 권장")
            out.append({"code": d.code, "name": d.name, "origin": d.origin, "score": round(score, 3), "why": why})
    return sorted(out, key=lambda x: -x["score"])[:3]


INTAKE_TASK = (
    "표 자료의 이름(name, 30자 이내) · 설명(description, 숫자 없이 한 문장)을 정하고, 열마다 한국어 업무 이름(label)과 의미(meaning, 20자 이내)를 쓴다. "
    "행 하나가 가리키는 업무 개체(entity)가 있으면 쓴다. 열 이름(name)은 입력 그대로. "
    'JSON: {"name":"…","description":"…","columns":[{"name":"…","label":"…","meaning":"…"}],"entity":"…|null"}'
)


def analyze_structured(session: Session, filename: str, content: bytes, *, origin: str = "bank", run_llm: bool = True) -> dict[str, Any]:
    from nhdip.graph.profile import profile_rows, rule_semantics

    from .datasets import IngestError, check_file, map_rows
    from .infer import _read, infer_definition

    try:
        raw, _parser = _read(content, filename)
    except Exception as exc:  # noqa: BLE001 — 읽지 못하는 표
        raise IngestError(f"표를 읽을 수 없습니다 — {exc}") from exc
    headers = list(raw[0].keys()) if raw else []
    matches = match_datasets(session, filename, headers)
    best = matches[0] if matches else None
    notes: list[str] = []
    if best and best["score"] >= 0.6:
        ds = session.get(Dataset, best["code"])
        chk = check_file(session, ds, filename, content)
        return {"kind": "structured", "mode": "existing", "target": ds.code, "targetName": ds.name, "origin": ds.origin, "matches": matches, "headers": headers[:80],
                "quality": chk["quality"], "rows": chk["rows"], "sample": chk["sample"][:5], "columns": chk["columns"], "notes": [f"기존 자료 '{ds.name}' 의 새 버전으로 올립니다 — {', '.join(best['why'])}"]}
    try:
        draft = infer_definition(content, filename, origin=origin)
    except IngestError as exc:
        if best:  # 원본 보고서 양식 등 — 가장 가까운 기존 정의로
            ds = session.get(Dataset, best["code"])
            chk = check_file(session, ds, filename, content)
            return {"kind": "structured", "mode": "existing", "target": ds.code, "targetName": ds.name, "origin": ds.origin, "matches": matches, "headers": headers[:80],
                    "quality": chk["quality"], "rows": chk["rows"], "sample": chk["sample"][:5], "columns": chk["columns"], "notes": [str(exc)]}
        raise
    definition = {k: draft[k] for k in ("code", "name", "origin", "kind", "description", "file_pattern", "refresh_cycle", "columns", "key_columns", "as_of_column", "quality_rules", "parser") if k in draft}
    # 같은 코드의 정의가 이미 있으면(예전 정의가 업무 구성 모양과 달라 새 정의를 만드는 경우 등) 뒤에 번호를 붙인다 — 반영 때 코드 충돌로 막히지 않게
    base, n = definition.get("code") or "", 2
    while base and session.get(Dataset, definition["code"]) is not None:
        definition["code"], n = f"{base}_{n}"[:60], n + 1
    tmp = SimpleNamespace(**{**definition, "mapping": {}, "materialize": False, "active": True})
    rows, _errs = map_rows(Dataset(**{**definition, "mapping": {}}), raw)
    prof = profile_rows(tmp, rows)
    sem: dict[str, Any] = rule_semantics(tmp, prof)
    meta: dict[str, Any] = {"by": "rule"}
    if run_llm:
        from nhdip.workflow.llm_judge import ask_json, clean_reason

        cols = [{"name": c["name"], "header": (c.get("aliases") or [c.get("label")])[0], "type": c.get("type"), "semantic": prof["columns"].get(c["name"], {}).get("semanticKo"),
                 "examples": [t["value"] for t in prof["columns"].get(c["name"], {}).get("top", [])[:3]]} for c in definition.get("columns") or []]
        existing = [{"code": d.code, "name": d.name} for d in session.execute(select(Dataset).where(Dataset.active).order_by(Dataset.code)).scalars()][:60]
        data, meta = ask_json(session, "data_intake", INTAKE_TASK, {"file": filename, "columns": cols, "existing": existing}, required=("columns",), shrink=("existing", "columns"))
        if data:
            by_name = {c["name"]: c for c in definition.get("columns") or []}
            sem_cols = dict(sem.get("columns") or {})
            for c in data.get("columns") or []:
                if isinstance(c, dict) and c.get("name") in by_name:
                    label, _ = clean_reason(c.get("label"), 40)
                    meaning, _ = clean_reason(c.get("meaning"), 40)
                    if label:
                        col = by_name[c["name"]]
                        orig = col.get("label")
                        if orig and orig != label and orig not in (col.get("aliases") or []):
                            # 원래 머리글은 별칭으로 남긴다 — 다음 달 같은 파일의 머리글 대응 · 업무 구성의 필요한 열 찾기가 라벨 변경에 흔들리지 않게
                            col["aliases"] = [*(col.get("aliases") or []), orig]
                        col["label"] = label
                    if meaning:
                        sem_cols[c["name"]] = {"meaning": meaning, "entity": None}
            name, _ = clean_reason(data.get("name"), 60)
            desc, _ = clean_reason(data.get("description"), 200)
            entity, _ = clean_reason(data.get("entity"), 30)
            if name:
                definition["name"] = name
            if desc:
                definition["description"] = desc
            sem = {**sem, "columns": sem_cols, "entity": entity or sem.get("entity"), "by": "llm"}
    chk = check_file(session, Dataset(**{**definition, "mapping": {}}), filename, content)
    notes = list(draft.get("notes") or [])
    return {"kind": "structured", "mode": "new", "target": definition.get("code"), "origin": definition.get("origin", origin), "matches": matches, "headers": headers[:80],
            "definition": definition, "samples": draft.get("samples"), "profile": {k: prof[k] for k in ("rows", "keyCandidates", "measures", "dimensions")},
            "profileColumns": {k: {kk: v.get(kk) for kk in ("semanticKo", "nullRate", "distinct", "baseType")} for k, v in prof["columns"].items()},
            "semantics": sem, "quality": chk["quality"], "rows": chk["rows"], "notes": notes, "llm": {k: meta.get(k) for k in ("by", "model", "reason")}}


# ═════════════════════════ 비정형 ═════════════════════════
DOC_TASK = (
    "문서의 제목(title, 80자 이내) · 문서 분류(doc_class — classes 의 code 만) · 발행 기관(issuer, 없으면 null) · 시행일(published_at, 본문에 있을 때만 YYYY-MM-DD, 없으면 null) · "
    "출처(origin: bank 당행 문서 | ext 외부 기관 문서) · 요약(summary, 숫자 없이 두 문장 이내)을 정한다. "
    'JSON: {"title":"…","doc_class":"…","issuer":"…|null","published_at":"…|null","origin":"bank|ext","summary":"…"}'
)


def doc_classes(session: Session) -> list[dict[str, str]]:
    labels = session.get(Setting, "doc_class.labels")
    origins = session.get(Setting, "doc_class.default_origin")
    lv = labels.value if labels is not None and isinstance(labels.value, dict) else {}
    ov = origins.value if origins is not None and isinstance(origins.value, dict) else {}
    return [{"code": k, "label": v, "origin": ov.get(k, "bank")} for k, v in lv.items()]


def _rule_doc(filename: str, body: str, classes: list[dict[str, str]]) -> dict[str, Any]:
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", (filename or "").rsplit("/", 1)[-1]).replace("_", " ").strip()
    first = next((ln.strip() for ln in (body or "").splitlines() if 4 <= len(ln.strip()) <= 80), "")
    title = (first or stem or "문서")[:80]
    head = (body or "")[:3000]
    hay = f"{filename} {head}"
    kw = {"gov_policy": ("금융위", "정책", "방안", "감독", "규정", "가이드라인", "금융당국"), "mgmt_decision": ("경영", "이사회", "결의", "전략", "사업계획", "경영목표"),
          "model_method": ("모형", "모델", "방법론", "PD", "검증"), "branch_ref": ("영업점", "지점", "공문", "업적평가")}
    scores = {c["code"]: sum(hay.count(w) for w in kw.get(c["code"], ())) for c in classes}
    code = max(scores, key=lambda k: scores[k]) if scores and max(scores.values()) > 0 else (classes[0]["code"] if classes else "reference")
    issuer = next((i for i in ISSUERS if i in head), None)
    m = DATE_RE.search(head)
    published = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31 else None
    origin = next((c["origin"] for c in classes if c["code"] == code), "bank")
    if issuer and issuer not in ("NH농협은행", "농협금융지주", "농협중앙회"):
        origin = "ext"
    return {"title": title, "doc_class": code, "issuer": issuer, "published_at": published, "origin": origin, "summary": ""}


def analyze_document(session: Session, filename: str, content: bytes, *, run_llm: bool = True) -> dict[str, Any]:
    from nhdip.privacy import mask_text

    from .documents import DocumentError, extract_text

    try:
        body, pages = extract_text(filename, content)
    except (DocumentError, ValueError) as exc:
        raise DocumentError(f"본문을 읽을 수 없습니다 — {exc}") from exc
    if not (body or "").strip():
        raise DocumentError("본문 텍스트가 비어 있습니다(스캔 PDF 는 OCR 후 올려 주세요)")
    classes = doc_classes(session)
    meta = _rule_doc(filename, body, classes)
    llm: dict[str, Any] = {"by": "rule"}
    if run_llm:
        from nhdip.workflow.llm_judge import ask_json, clean_reason

        data, llm = ask_json(session, "doc_intake", DOC_TASK, {"file": filename, "classes": [{"code": c["code"], "label": c["label"]} for c in classes], "text": mask_text(body[:5000])}, shrink=())
        if data:
            codes = {c["code"] for c in classes}
            title = str(data.get("title") or "").strip()[:120]
            if title:
                meta["title"] = title
            if data.get("doc_class") in codes:
                meta["doc_class"] = data["doc_class"]
            if isinstance(data.get("issuer"), str) and data["issuer"].strip():
                meta["issuer"] = data["issuer"].strip()[:120]
            if isinstance(data.get("published_at"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["published_at"]):
                meta["published_at"] = data["published_at"]
            if data.get("origin") in ("bank", "ext"):
                meta["origin"] = data["origin"]
            summary, _ = clean_reason(data.get("summary"), 300)
            meta["summary"] = summary
    return {"kind": "unstructured", "mode": "document", "target": meta["doc_class"], "origin": meta["origin"], "document": meta, "classes": classes,
            "chars": len(body), "pages": len(pages or []) or 1, "excerpt": mask_text(body.strip()[:500]), "llm": {k: llm.get(k) for k in ("by", "model", "reason")}}


# ═════════════════════════ 반영 상태 (DOB-06) ═════════════════════════
def storage_status(session: Session, r: Any) -> list[dict[str, Any]]:
    """[{key, label, state(done · active · warn · skip · idle), detail}] — 반영된 등록 건이 어느 저장소 · 에이전트 단계까지 갔는지."""
    from nhdip.models import AgentDecision, DataProfile, OutboxEvent, WorkflowRun, source

    res = r.result or {}
    stages: list[dict[str, Any]] = []

    def add(key: str, label: str, state: str, detail: str) -> None:
        stages.append({"key": key, "label": label, "state": state, "detail": detail})

    if r.status != "approved":
        add("ledger", "원장 저장", "idle" if r.status in ("draft", "pending") else "skip", {"draft": "확인 후 반영 전", "pending": "승인 대기", "rejected": "반려", "failed": "반영 실패", "discarded": "버림"}.get(r.status, r.status))
        return stages
    events: list[Any] = []
    if r.kind == "dataset":
        t = source(r.origin or "bank")
        v = session.get(t.version, res.get("versionId")) if res.get("versionId") else None
        add("ledger", "PostgreSQL 원장", "done" if v is not None and v.status == "committed" else "warn", f"v{res.get('version')} · {res.get('rows')}행 · 품질 {res.get('quality')}" + (" · 현재 버전" if v is not None and v.is_current else ""))
        prof = session.execute(select(DataProfile).where(DataProfile.dataset_code == r.target).order_by(DataProfile.created_at.desc()).limit(1)).scalars().first()
        add("profile", "구조 파악(온톨로지 구축)", "done" if prof is not None else "active", f"열 {len((prof.profile or {}).get('columns') or {})}개 · {prof.by}" if prof is not None else "구축 워크플로가 곧 파악합니다")
        props = session.execute(select(func.count()).select_from(AgentDecision).where(AgentDecision.workflow_code == "wf_ontology_build", AgentDecision.decision.in_(["object_type", "link"]), AgentDecision.detail["dataset"].astext == r.target)).scalar() or 0
        add("ontology", "객체 유형 · 링크 제안", "done" if props else "idle", f"제안 {props}건 — [온톨로지 › 변경 제안]에서 승인" if props else "제안 없음(이미 연결됐거나 대기)")
        from nhdip.models import KbChunk

        card = session.execute(select(func.count()).select_from(KbChunk).where(KbChunk.source_key == f"dataset:{r.target}")).scalar() or 0
        add("catalog", "AI 어시스턴트 자료 카드", "done" if card else "active", "색인됨 — 질문에서 찾을 수 있음" if card else "워커 대조가 곧 색인합니다")
        if v is not None:
            events = session.execute(select(OutboxEvent).where(OutboxEvent.type == "dataset.committed", OutboxEvent.payload["version_id"].astext == str(v.id))).scalars().all()
    else:
        t = source(r.origin or "bank")
        doc = session.get(t.document, res.get("documentId")) if res.get("documentId") else None
        if doc is None:
            add("ledger", "PostgreSQL 문서", "warn", "문서를 찾을 수 없음(삭제됐을 수 있음)")
            return stages
        n = session.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == doc.id)).scalar() or 0
        emb = session.execute(select(func.count()).select_from(t.chunk).where(t.chunk.document_id == doc.id, t.chunk.embedding.is_not(None))).scalar() or 0
        add("ledger", "PostgreSQL 문서 · 청크", "done", f"{doc.doc_code} v{doc.version} · 청크 {n}개")
        add("vector", "pgvector 임베딩", "done" if n and emb == n else ("active" if emb else "warn"), f"{emb}/{n} 청크" + ("" if emb else " — 임베딩 모델 미설정이면 키워드 검색만"))
        try:
            from nhdip.knowledge.elastic import configured as es_configured

            es_on = bool(es_configured())
        except Exception:  # noqa: BLE001
            es_on = False
        add("search", "Elasticsearch 문서 색인", "active" if es_on else "skip", "워커 동기화(1분 주기)" if es_on else "ES 미구성 — PostgreSQL 검색으로 대체")
        ex = doc.extraction or {}
        add("extract", "온톨로지 구조화(문서 추출)", "done" if ex else "active", f"개체 {len(ex.get('entities') or [])} · 관계 {len(ex.get('relations') or [])} · {ex.get('by')}" if ex else "그래프 투영 워크플로가 곧 추출합니다")
        events = session.execute(select(OutboxEvent).where(OutboxEvent.type == "document.ingested", OutboxEvent.payload["document_id"].astext == str(doc.id))).scalars().all()
    wfs: list[str] = []
    for e in events:
        wfs += [m.get("workflow") for m in e.matched or [] if isinstance(m, dict) and m.get("workflow") and not str(m.get("workflow")).startswith("(")]
    runs = []
    for wf in dict.fromkeys(wfs):
        run = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == wf, WorkflowRun.started_at >= (r.reviewed_at or r.created_at)).order_by(WorkflowRun.started_at.asc()).limit(1)).scalars().first()
        runs.append(f"{wf}:{run.status if run else '대기'}")
    graph = next((x for x in runs if x.startswith("wf_graph_projection")), None)
    add("graph", "Neo4j 그래프 투영", "done" if graph and graph.endswith(("succeeded",)) else ("warn" if graph and graph.endswith("degraded") else "active"), graph or "투영 대기")
    add("workflows", "이어진 워크플로", "done" if runs and all(not x.endswith("대기") for x in runs) else ("active" if events and not any(e.dispatched_at for e in events) else ("idle" if not runs else "active")), " · ".join(runs) or ("분배 대기" if events else "연결된 워크플로 없음"))
    return stages
