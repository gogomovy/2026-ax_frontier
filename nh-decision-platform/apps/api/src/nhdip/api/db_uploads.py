"""업무 자료 등록 요청 · 관리자 승인 (Phase C · UPL-01~03 · Q99).

- 업무 사용자(화면 리소스 `db_upload`)는 [데이터베이스]에서 정형 자료(기존 데이터셋의 새 버전)나 문서를 올린다.
  올리는 즉시 업로드 보안 검사 · 형식 · 품질 검사를 하고(저장 · 이벤트 없음) 결과와 함께 '승인 대기' 요청으로 남긴다.
  품질 실패 자료는 요청 단계에서 거절한다.
- 관리자가 승인하면 관리자 직접 업로드와 같은 확정 경로(`ingest_file` · `ingest_document`)를 탄다 → 현재 버전 · 이벤트 · 관련 워크플로.
  반려는 사유 필수, 아무 데이터도 바뀌지 않는다.
- 감사: `db.upload.request` · `db.upload.approve` | `db.upload.reject` · `db.upload.applied` | `db.upload.failed`.
- 올릴 수 있는 대상은 설정 `upload.user_targets` (`{"datasets": "*" | [코드…], "doc_classes": "*" | [분류…]}`).
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.data.datasets import IngestError, check_file, current_versions, ingest_file
from nhdip.data.documents import DocumentError, extract_text, ingest_document
from nhdip.db import get_session
from nhdip.data.infer import infer_definition, validate_definition
from nhdip.events import audit, emit
from nhdip.models import AppUser, Dataset, OrgUnit, Setting, UploadRequest, utcnow

from .admin_data import _read as read_upload
from .deps import client_ip, current_user, require_admin, require_resource

router = APIRouter(tags=["db"])
admin_router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# new_datasets: 기존에 없는 새 종류 자료를 올릴 때 파일에서 추론한 정의를 제안해 승인받을 수 있는가 (DEF-03)
_DEFAULT_TARGETS: dict[str, Any] = {"datasets": "*", "doc_classes": "*", "new_datasets": True}
# 제안 정의에서 저장하는 필드 — 매핑(온톨로지 투영)은 관리자가 따로 정하므로 제안에서는 받지 않는다
PROPOSAL_FIELDS = ("code", "name", "origin", "kind", "description", "file_pattern", "refresh_cycle", "columns", "key_columns", "as_of_column", "quality_rules", "parser")
STATUS_LABEL = {"pending": "승인 대기", "approved": "승인 · 반영", "rejected": "반려", "failed": "반영 실패", "draft": "확인 중(초안)", "discarded": "버림"}


def _iso(v):
    return v.isoformat() if v else None


def _targets(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "upload.user_targets")
    v = s.value if s is not None and isinstance(s.value, dict) else {}
    return {**_DEFAULT_TARGETS, **v}


def _allowed(spec: Any, key: str) -> bool:
    return spec == "*" or (isinstance(spec, list) and key in spec)


def _doc_classes(session: Session, user: AppUser | None = None) -> list[dict[str, str]]:
    """올릴 수 있는 문서 분류 — 공통 통합 DB 분류는 관리자에게만(§38 CMN)."""
    from nhdip.common_db import common_doc_classes

    labels = session.get(Setting, "doc_class.labels")
    origins = session.get(Setting, "doc_class.default_origin")
    lab = labels.value if labels is not None and isinstance(labels.value, dict) else {}
    org = origins.value if origins is not None and isinstance(origins.value, dict) else {}
    allow = _targets(session)["doc_classes"]
    hide = set() if getattr(user, "role", None) == "admin" else set(common_doc_classes(session))
    return [{"key": k, "label": str(v), "origin": str(org.get(k, "bank"))} for k, v in lab.items() if _allowed(allow, k) and k not in hide]


def _no_common(user: AppUser, *, dataset: Any = None, doc_class: str | None = None, session: Session | None = None) -> None:
    from nhdip.common_db import CommonOnly, assert_can_upload

    try:
        assert_can_upload(user, dataset=dataset, doc_class=doc_class, session=session)
    except CommonOnly as exc:
        raise HTTPException(403, str(exc)) from exc


def _store(user: str, name: str, content: bytes) -> tuple[str, str]:
    """요청 파일은 파일 저장소 `requests/` 에 둔다(승인 때 다시 읽음). 저장소에 쓸 수 없으면 요청을 받지 않는다(503)."""
    sha = hashlib.sha256(content).hexdigest()
    base = os.path.join(get_settings().filestore_dir, "requests")
    safe = re.sub(r"[^0-9A-Za-z가-힣._()\-]+", "_", os.path.basename(name))[:120] or "upload"
    path = os.path.join(base, f"{sha[:16]}_{user}_{safe}")
    try:
        os.makedirs(base, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        raise HTTPException(503, "파일 저장소에 쓸 수 없어 요청을 받지 못했습니다 — 관리자에게 알려 주세요(FILESTORE_DIR 권한, 관리자 [시스템 상태] 운영 준비 점검)") from exc
    return sha, path


def _names(session: Session, emps: set[str]) -> dict[str, str]:
    if not emps:
        return {}
    return dict(session.execute(select(AppUser.emp_no, AppUser.name).where(AppUser.emp_no.in_(emps))).all())


def _req_json(r: UploadRequest, names: dict[str, str] | None = None, orgs: dict[str, str] | None = None, full: bool = False) -> dict[str, Any]:
    names = names or {}
    out = {
        "id": r.id,
        "kind": r.kind,
        "target": r.target,
        "targetLabel": (r.meta or {}).get("targetLabel") or r.target,
        "origin": r.origin,
        "fileName": r.file_name,
        "meta": {k: v for k, v in (r.meta or {}).items() if k != "text"},
        "preview": {k: v for k, v in (r.preview or {}).items() if full or k != "sample"},
        "status": r.status,
        "statusLabel": STATUS_LABEL.get(r.status, r.status),
        "requestedBy": r.requested_by,
        "requestedByName": names.get(r.requested_by),
        "requestedOrg": r.requested_org,
        "requestedOrgName": (orgs or {}).get(r.requested_org or ""),
        "reviewedBy": r.reviewed_by,
        "reviewedByName": names.get(r.reviewed_by or ""),
        "reviewedAt": _iso(r.reviewed_at),
        "reviewNote": r.review_note,
        "result": r.result or {},
        "createdAt": _iso(r.created_at),
    }
    return out


def _dataset_for_user(session: Session, code: str) -> Dataset:
    d = session.get(Dataset, code)
    if d is None or not getattr(d, "active", True):
        raise HTTPException(404, "데이터셋 없음")
    if not _allowed(_targets(session)["datasets"], code):
        raise HTTPException(403, "이 데이터셋은 업무 화면에서 올릴 수 없습니다 — 관리자에게 요청하세요")
    if getattr(d, "common", False):
        raise HTTPException(403, "공통 통합 DB 자료는 관리자만 올릴 수 있습니다 — 관리자에게 요청하세요")
    return d


# ═════════════════════════ 업무 사용자 ═════════════════════════
@router.get("/db/uploadable")
def uploadable(user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    """올릴 수 있는 데이터셋(현재 버전 요약) · 문서 분류 · 파일 형식."""
    allow = _targets(session)["datasets"]
    out = []
    for d in session.execute(select(Dataset).order_by(Dataset.origin, Dataset.code)).scalars():
        if not getattr(d, "active", True) or not _allowed(allow, d.code) or (getattr(d, "common", False) and user.role != "admin"):
            continue
        cur = current_versions(session, d)
        out.append({
            "code": d.code, "name": d.name, "origin": d.origin, "kind": d.kind, "description": d.description,
            "filePattern": d.file_pattern, "refreshCycle": d.refresh_cycle,
            "columns": [{"name": c.get("name"), "label": c.get("label") or c.get("description") or "", "type": c.get("type")} for c in (d.columns or [])][:60],
            "current": [{"version": v.version, "asOf": _iso(v.as_of), "rows": v.row_count, "dataOrigin": v.data_origin, "memo": getattr(v, "memo", None)} for v in cur[:3]],
            "periodCount": len({v.as_of for v in cur}), "asOfColumn": d.as_of_column,  # 보관 중인 기준일 수 (Phase P · UPV-07)
        })
    pol = session.get(Setting, "upload.policy")
    max_mb = (pol.value or {}).get("max_mb") if pol is not None and isinstance(pol.value, dict) else None
    return {
        "datasets": out,
        "docClasses": _doc_classes(session, user),
        "canPropose": bool(_targets(session).get("new_datasets", True)),
        # .md 는 두 쪽 모두 — 표가 있으면 정형 자료, 없으면 문서(화면이 내용을 보고 고른다 · Phase Q MD-04)
        "accept": {"dataset": ".csv,.tsv,.xlsx,.json,.md", "document": ".pdf,.docx,.hwpx,.hwp,.txt,.md,.html"},
        # 파일 놓기 영역이 먼저 알려 주는 용량 한도(Phase E · UXF-01) — 실제 차단은 서버 보안 검사
        "maxMb": int(max_mb) if isinstance(max_mb, (int, float)) else 50,
    }


@router.get("/db/datasets/{code}/periods")
def dataset_periods(code: str, user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    """보관 중인 기준일 (Phase P · UPV-07) — 같은 자료를 날짜만 바꿔 올릴 때 어떤 기준일 판이 있는지(판 · 행 · 메모 · 반영일 · 소유)와 최근 판 이력."""
    from nhdip.orgs import owner_json

    d = session.get(Dataset, code)
    if d is None or not getattr(d, "active", True) or not _allowed(_targets(session)["datasets"], code) or (getattr(d, "common", False) and user.role != "admin"):
        raise HTTPException(404, "데이터셋 없음")
    from nhdip.models import source as _src

    t = _src(d.origin)
    vs = session.execute(select(t.version).where(t.version.dataset_code == code, t.version.status != "deleted").order_by(t.version.version.desc()).limit(40)).scalars().all()
    emps = {v.requested_by for v in vs if getattr(v, "requested_by", None)} | {v.uploaded_by for v in vs if v.uploaded_by}
    names = _names(session, {e for e in emps if e})
    cache: dict[str, Any] = {}

    def j(v: Any) -> dict[str, Any]:
        req = getattr(v, "requested_by", None) or v.uploaded_by
        return {"version": v.version, "asOf": _iso(v.as_of), "status": v.status, "isCurrent": v.is_current, "rows": v.row_count, "memo": getattr(v, "memo", None),
                "requestedBy": req, "requestedByName": names.get(req or ""), "committedAt": _iso(v.committed_at), "owner": owner_json(session, v.owner_org, cache), "fileName": v.file_name,
                "dataOrigin": v.data_origin}

    cur = sorted([j(v) for v in vs if v.is_current], key=lambda p: (p["asOf"] or "", p["version"]))
    return {"dataset": d.code, "name": d.name, "asOfColumn": d.as_of_column, "periods": cur, "history": [j(v) for v in vs[:20]],
            "rule": "같은 자료의 판은 기준일(영업점 자료는 영업점마다)로 구분됩니다 — 기준일이 같으면 새 판으로 교체, 다르면 날짜별로 함께 보관. 메모는 판 설명입니다."}


AUTO_MATCH_MIN = 0.6  # 파일 이름 규칙이 맞거나 머리글이 충분히 겹치면 기존 자료의 새 버전 (자료 등록 에이전트와 같은 기준)


def auto_target(session: Session, filename: str, content: bytes, *, include_common: bool = False) -> tuple[Dataset | None, list[dict[str, Any]]]:
    """대상을 고르지 않고 올린 파일 — 기존 정의 중 맞는 것(파일 이름 규칙 · 머리글 겹침). 없으면 (None, 후보).
    공통 통합 DB 자료는 관리자 올리기(include_common=True)에서만 대상이 된다(§38 CMN)."""
    from nhdip.data.infer import _read
    from nhdip.data.onboarding import match_datasets

    try:
        raw, _ = _read(content, filename)
        headers = [str(h) for h in raw[0].keys()] if raw else []
    except Exception:  # noqa: BLE001 — 원본 보고서 양식 등 일반 표로 못 읽는 파일은 이름 규칙만으로
        headers = []
    matches = match_datasets(session, filename, headers)
    allow = _targets(session)["datasets"]
    for m in matches:
        if m["score"] >= AUTO_MATCH_MIN and _allowed(allow, m["code"]):
            d = session.get(Dataset, m["code"])
            if d is not None and getattr(d, "active", True):
                if getattr(d, "common", False) and not include_common:
                    raise HTTPException(403, f"이 파일은 공통 통합 DB 자료 '{d.name}' 입니다 — 공통 자료는 관리자만 올릴 수 있습니다")
                return d, matches
    return None, matches


def inferred_proposal(session: Session, filename: str, content: bytes, origin: str) -> dict[str, Any]:
    """맞는 정의가 없는 파일 → 파일에서 추론한 정의(제안) — 승인되면 이 정의로 데이터셋이 만들어진다 (M.24 · DOB-16)."""
    from nhdip.data.infer import infer_definition

    try:
        out = infer_definition(content, filename, origin=origin)
    except (IngestError, ValueError) as exc:
        raise HTTPException(422, f"맞는 자료가 없어 파일에서 정의를 만들려 했지만 읽을 수 없습니다 — {exc}") from exc
    base, n = out["code"], 2
    while session.get(Dataset, out["code"]) is not None or _pending_proposal(session, out["code"]):
        out["code"], n = f"{base}_{n}"[:60], n + 1
    d = {k: out[k] for k in PROPOSAL_FIELDS if k in out}
    problems = validate_definition(d)
    if problems:
        raise HTTPException(422, "파일에서 만든 정의에 문제가 있습니다 — " + " · ".join(problems[:4]))
    return d


@router.post("/db/uploads/dataset", status_code=201)
async def request_dataset(
    request: Request,
    target: str | None = Form(None),
    file: UploadFile = File(...),
    data_origin: str = Form("actual"),
    as_of: str | None = Form(None),
    note: str | None = Form(None),
    origin: str = Form("bank"),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    """자료 올리기 — 대상(target)을 고르면 그 자료의 새 버전으로 요청. 고르지 않으면(M.24) 맞는 정의를 찾아 그 자료로, 없으면 파일에서 정의를
    만들어 '새 종류 자료' 로 요청한다(승인되면 정의가 만들어지고 이 파일이 첫 버전). 정의를 미리 만들어 둘 필요가 없다."""
    if data_origin not in ("actual", "simulated"):
        raise HTTPException(422, "data_origin 은 actual | simulated")
    if as_of and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise HTTPException(422, "기준일은 YYYY-MM-DD 형식입니다")
    if origin not in ("bank", "ext"):
        raise HTTPException(422, "origin 은 bank(당행) | ext(외부)")
    d = _dataset_for_user(session, target) if target else None
    name, content = await read_upload(file, "dataset", session, request, user.emp_no)
    if d is None:
        d, _matches = auto_target(session, name, content)
    if d is None:
        _can_propose(session)
        proposal = inferred_proposal(session, name, content, origin)
        return _proposal_request(session, request, user, proposal, name, content, data_origin, as_of, note, auto=True)
    try:
        pv = check_file(session, d, name, content, as_of=as_of, owner_org=user.org_code, place=True)
    except (IngestError, ValueError) as exc:
        raise HTTPException(422, f"파일을 읽을 수 없습니다 — {exc}") from exc
    if (pv.get("placement") or {}).get("error"):
        # 입력 기준일 ≠ 파일 기간 (UPV-03) — 다른 달 판을 잘못 교체하지 않게
        raise HTTPException(422, pv["placement"]["error"])
    q = pv["quality"]
    if q.get("status") == "failed":
        bad = [f"{c['rule']}: {c['detail']}" for c in q.get("checks", []) if not c.get("passed") and c.get("severity") == "error"][:5]
        audit(session, user.emp_no, "db.upload.rejected_quality", "dataset", d.code, {"file": name, "checks": bad}, client_ip(request))
        session.commit()
        raise HTTPException(422, "품질 검사를 통과하지 못해 요청하지 않았습니다 — " + " · ".join(bad))
    sha, path = _store(user.emp_no, name, content)
    r = UploadRequest(
        kind="dataset", target=d.code, origin=d.origin, file_name=name, file_path=path, file_sha256=sha,
        meta={"targetLabel": d.name, "asOf": as_of or None, "dataOrigin": data_origin, "note": (note or "")[:500]},
        preview={"rows": pv["rows"], "quality": {"status": q.get("status"), "checks": q.get("checks", []), "source": q.get("source")}, "headers": pv["headers"][:60], "columns": pv["columns"][:60], "sample": pv["sample"],
                 "placement": pv.get("placement")},
        status="pending", requested_by=user.emp_no, requested_org=user.org_code,
    )
    session.add(r)
    session.flush()
    audit(session, user.emp_no, "db.upload.request", "upload_request", str(r.id), {"kind": "dataset", "target": d.code, "file": name, "rows": pv["rows"], "quality": q.get("status")}, client_ip(request))
    session.commit()
    return _req_json(r, full=True)


def _can_propose(session: Session) -> None:
    if not _targets(session).get("new_datasets", True):
        raise HTTPException(403, "새 종류 자료 제안은 막혀 있습니다 — 관리자에게 데이터셋 등록을 요청하세요")


@router.post("/db/uploads/dataset-infer")
async def infer_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    origin: str = Form("bank"),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    """맞는 데이터셋이 없는 새 파일 → 파일에서 추론한 정의 초안(열 · 타입 · 키 · 기준일 열). 저장하지 않는다 — 확인 · 수정해 `dataset-proposal` 로 제안."""
    _can_propose(session)
    fname, content = await read_upload(file, "dataset", session, request, user.emp_no)
    try:
        out = infer_definition(content, fname, name=name, origin=origin)
    except (IngestError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    base, n = out["code"], 2
    while session.get(Dataset, out["code"]) is not None or _pending_proposal(session, out["code"]):
        out["code"], n = f"{base}_{n}"[:60], n + 1  # 이미 있거나 제안 중인 코드와 겹치지 않게
    out["codeAdjusted"] = out["code"] != base
    return out


def _pending_proposal(session: Session, code: str) -> bool:
    q = select(UploadRequest.id).where(UploadRequest.kind == "dataset", UploadRequest.target == code, UploadRequest.status == "pending", UploadRequest.meta["proposal"].astext.is_not(None)).limit(1)
    return session.execute(q).first() is not None


@router.post("/db/uploads/dataset-proposal", status_code=201)
async def propose_dataset(
    request: Request,
    file: UploadFile = File(...),
    definition: str = Form(...),
    data_origin: str = Form("actual"),
    as_of: str | None = Form(None),
    note: str | None = Form(None),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    """새 종류 자료 등록 요청 — 확인 · 수정한 정의와 파일을 함께 보낸다. 같은 검사(보안 · 형식 · 품질 · 개인정보)를 하고, 승인되면 데이터셋이 만들어지며 이 파일이 첫 버전이 된다."""
    import json

    _can_propose(session)
    try:
        raw_def = json.loads(definition)
        if not isinstance(raw_def, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "definition 은 JSON 객체여야 합니다") from exc
    d = {k: raw_def[k] for k in PROPOSAL_FIELDS if k in raw_def}
    d.setdefault("kind", "fact")
    for k, dflt in (("description", ""), ("columns", []), ("key_columns", []), ("quality_rules", []), ("parser", {})):
        d.setdefault(k, dflt)
    problems = validate_definition(d)
    if d.get("kind") not in ("fact", "master"):
        problems.append("자료 종류는 fact | master 입니다")
    if d.get("file_pattern"):
        try:
            re.compile(str(d["file_pattern"]))
        except re.error:
            problems.append("파일 이름 규칙(정규식)이 올바르지 않습니다")
    if problems:
        raise HTTPException(422, " · ".join(problems[:6]))
    if data_origin not in ("actual", "simulated"):
        raise HTTPException(422, "data_origin 은 actual | simulated")
    if as_of and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
        raise HTTPException(422, "기준일은 YYYY-MM-DD 형식입니다")
    code = str(d["code"])
    if session.get(Dataset, code) is not None or _pending_proposal(session, code):
        raise HTTPException(409, "이미 있거나 제안 중인 데이터셋 코드입니다 — 코드를 바꾸거나 목록에서 그 자료를 고르세요")
    fname, content = await read_upload(file, "dataset", session, request, user.emp_no)
    return _proposal_request(session, request, user, d, fname, content, data_origin, as_of, note)


def _proposal_request(session: Session, request: Request, user: AppUser, d: dict[str, Any], fname: str, content: bytes, data_origin: str, as_of: str | None, note: str | None, *, auto: bool = False) -> dict[str, Any]:
    """새 종류 자료 요청 — 정의(제안)로 같은 검사를 하고 요청을 남긴다. 승인(do_approve)에서 정의를 만들고 이 파일을 첫 버전으로 올린다."""
    code = str(d["code"])
    ds = Dataset(**d, mapping={}, active=True)  # 저장하지 않는 임시 정의 — 같은 검사를 통과하는지 본다
    try:
        pv = check_file(session, ds, fname, content, as_of=as_of, owner_org=user.org_code, place=True)
    except (IngestError, ValueError) as exc:
        raise HTTPException(422, f"파일을 이 정의로 읽을 수 없습니다 — {exc}") from exc
    if (pv.get("placement") or {}).get("error"):
        raise HTTPException(422, pv["placement"]["error"])
    q = pv["quality"]
    if q.get("status") == "failed":
        bad = [f"{c['rule']}: {c['detail']}" for c in q.get("checks", []) if not c.get("passed") and c.get("severity") == "error"][:5]
        audit(session, user.emp_no, "db.upload.rejected_quality", "dataset", code, {"file": fname, "checks": bad, "proposal": True}, client_ip(request))
        session.commit()
        raise HTTPException(422, "품질 검사를 통과하지 못해 요청하지 않았습니다 — " + " · ".join(bad))
    sha, path = _store(user.emp_no, fname, content)
    r = UploadRequest(
        kind="dataset", target=code, origin=str(d["origin"]), file_name=fname, file_path=path, file_sha256=sha,
        meta={"targetLabel": str(d["name"]), "asOf": as_of or None, "dataOrigin": data_origin, "note": (note or "")[:500], "proposal": d, **({"autoDefinition": True} if auto else {})},
        preview={"rows": pv["rows"], "quality": {"status": q.get("status"), "checks": q.get("checks", []), "source": q.get("source")}, "headers": pv["headers"][:60], "columns": pv["columns"][:60], "sample": pv["sample"],
                 "placement": pv.get("placement")},
        status="pending", requested_by=user.emp_no, requested_org=user.org_code,
    )
    session.add(r)
    session.flush()
    audit(session, user.emp_no, "db.upload.request", "upload_request", str(r.id), {"kind": "dataset", "target": code, "file": fname, "rows": pv["rows"], "quality": q.get("status"), "proposal": True, "auto": auto, "columns": len(d["columns"])}, client_ip(request))
    session.commit()
    return _req_json(r, full=True)


@router.post("/db/uploads/document", status_code=201)
async def request_document(
    request: Request,
    doc_class: str = Form(...),
    title: str = Form(...),
    issuer: str | None = Form(None),
    published_at: str | None = Form(None),
    text: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    classes = {c["key"]: c for c in _doc_classes(session, user)}
    if doc_class not in classes:
        raise HTTPException(422, "올릴 수 없는 문서 분류입니다")
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise HTTPException(422, "제목은 1~200자입니다")
    if published_at and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_at):
        raise HTTPException(422, "시행일은 YYYY-MM-DD 형식입니다")
    if file is not None and file.filename:
        name, content = await read_upload(file, "document", session, request, user.emp_no)
    elif (text or "").strip():
        name, content = f"{re.sub(r'[^0-9A-Za-z가-힣]+', '_', title)[:60] or 'document'}.txt", (text or "").encode("utf-8")
    else:
        raise HTTPException(422, "파일이나 본문을 넣어 주세요")
    try:
        body, pages = extract_text(name, content)
    except (DocumentError, ValueError) as exc:
        raise HTTPException(422, f"본문을 읽을 수 없습니다 — {exc}") from exc
    if not (body or "").strip():
        raise HTTPException(422, "본문 텍스트가 비어 있습니다(스캔 PDF 는 OCR 후 올려 주세요)")
    sha, path = _store(user.emp_no, name, content)
    cls = classes[doc_class]
    r = UploadRequest(
        kind="document", target=doc_class, origin=cls["origin"], file_name=name, file_path=path, file_sha256=sha,
        meta={"targetLabel": cls["label"], "title": title, "issuer": (issuer or "")[:120] or None, "publishedAt": published_at or None, "note": (note or "")[:500]},
        preview={"chars": len(body), "pages": len(pages or []) or 1, "excerpt": body.strip()[:400]},
        status="pending", requested_by=user.emp_no, requested_org=user.org_code,
    )
    session.add(r)
    session.flush()
    audit(session, user.emp_no, "db.upload.request", "upload_request", str(r.id), {"kind": "document", "target": doc_class, "title": title, "file": name}, client_ip(request))
    session.commit()
    return _req_json(r, full=True)


@router.get("/db/uploads/mine")
def my_uploads(user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    rows = session.execute(select(UploadRequest).where(UploadRequest.requested_by == user.emp_no).order_by(UploadRequest.id.desc()).limit(50)).scalars().all()
    names = _names(session, {r.reviewed_by for r in rows if r.reviewed_by})
    return [_req_json(r, names) for r in rows]


# ═════════════════════════ 검토(관리자 · 부서 데이터 책임자) ═════════════════════════
class ReviewIn(BaseModel):
    note: str | None = None
    force: bool = False


def _pending(session: Session, rid: int) -> UploadRequest:
    r = session.get(UploadRequest, rid, with_for_update=True)
    if r is None:
        raise HTTPException(404, "요청 없음")
    if r.status != "pending":
        raise HTTPException(409, f"이미 처리된 요청입니다 ({STATUS_LABEL.get(r.status, r.status)})")
    return r


def _list(session: Session, q, full: bool = True) -> list[dict[str, Any]]:
    rows = session.execute(q).scalars().all()
    names = _names(session, {r.requested_by for r in rows} | {r.reviewed_by for r in rows if r.reviewed_by})
    orgs = dict(session.execute(select(OrgUnit.code, OrgUnit.name).where(OrgUnit.code.in_({r.requested_org for r in rows if r.requested_org}))).all()) if rows else {}
    return [_req_json(r, names, orgs, full=full) for r in rows]


def _counts(session: Session, where=None) -> dict[str, int]:
    counts = {k: 0 for k in STATUS_LABEL}
    q = select(UploadRequest.status)
    if where is not None:
        q = q.where(where)
    for (st,) in session.execute(q).all():
        counts[st] = counts.get(st, 0) + 1
    return counts


def do_approve(session: Session, r: UploadRequest, actor: AppUser, body: ReviewIn, ip: str | None, via: str) -> dict[str, Any]:
    """승인 — 관리자 직접 업로드와 같은 확정 경로(저장점 안). 실패하면 요청만 failed 로 남긴다."""
    try:
        with open(r.file_path, "rb") as fh:
            content = fh.read()
    except OSError as exc:
        raise HTTPException(410, "요청 파일을 찾을 수 없습니다 — 다시 올려 달라고 요청하세요") from exc
    if r.file_sha256 and hashlib.sha256(content).hexdigest() != r.file_sha256:
        raise HTTPException(409, "요청 파일이 바뀌었습니다(해시 불일치) — 반려 후 다시 올려 달라고 요청하세요")
    meta = r.meta or {}
    note = f"업무 자료 요청 #{r.id} ({r.requested_by}) 승인" + (" · 부서 데이터 책임자" if via == "steward" else "") + (f" — {meta.get('note')}" if meta.get("note") else "")
    # 공통 통합 DB 는 관리자만 반영한다(§38 CMN) — 부서 책임자 승인 · 직접 반영으로 들어가지 않게
    if r.kind == "dataset":
        _no_common(actor, dataset=session.get(Dataset, r.target))
    else:
        _no_common(actor, doc_class=r.target, session=session)
    sp = session.begin_nested()
    try:
        if r.kind == "dataset":
            d = session.get(Dataset, r.target)
            proposal = meta.get("proposal") if isinstance(meta.get("proposal"), dict) else None
            created = False
            if proposal is not None and d is not None:
                raise IngestError("같은 코드의 데이터셋이 이미 만들어졌습니다 — 반려하고 그 자료로 다시 올려 달라고 하세요")
            if d is None:
                if proposal is None:
                    raise IngestError("데이터셋이 없어졌습니다")
                problems = validate_definition(proposal)
                if problems:
                    raise IngestError("제안한 정의에 문제가 있습니다 — " + " · ".join(problems[:4]))
                # 새 종류 자료 — 제안한 정의로 데이터셋을 만든 뒤 이 파일을 첫 버전으로 올린다(아래 어느 단계가 실패해도 savepoint 로 함께 되돌린다)
                d = Dataset(**{k: proposal[k] for k in PROPOSAL_FIELDS if k in proposal}, mapping={}, active=True)
                session.add(d)
                session.flush()
                emit(session, "config.changed", {"kind": "dataset", "code": d.code}, actor.emp_no)
                audit(session, actor.emp_no, "db.dataset.create_by_request", "dataset", d.code, {"request": r.id, "columns": len(d.columns), "keys": d.key_columns, "via": via}, ip)
                created = True
            v = ingest_file(session, d, r.file_name, content, as_of=meta.get("asOf") or None, data_origin=meta.get("dataOrigin") or "actual", actor=actor.emp_no, note=note, force=bool(body.force),
                            owner_org=r.requested_org,  # 소유 = 요청한 사람의 소속 팀(승인한 사람이 아니라)
                            memo=meta.get("note") or None, requested_by=r.requested_by)  # 요청자 메모 · 요청자는 판에 따로 (UPV-06)
            result = {"version": v.version, "versionId": v.id, "status": v.status, "rows": v.row_count, "quality": (v.quality or {}).get("status"), "isCurrent": v.is_current, **({"createdDataset": d.code} if created else {})}
            if v.status != "committed":
                raise IngestError(f"품질 검사 실패로 확정되지 않았습니다(v{v.version}) — 필요하면 '품질 실패여도 확정' 으로 승인")
        else:
            title = str(meta.get("title") or r.file_name)
            code = "doc-" + re.sub(r"[^0-9A-Za-z가-힣]+", "-", title)[:60].strip("-").lower()
            doc = ingest_document(
                session, origin=r.origin, doc_code=code, title=title, doc_class=r.target, filename=r.file_name, content=content,
                issuer=meta.get("issuer"), published_at=meta.get("publishedAt"),
                meta={"docType": "업무 등록 문서", "isOfficial": r.origin == "ext", "requestedBy": r.requested_by, "uploadRequest": r.id}, actor=actor.emp_no,
                owner_org=r.requested_org,
            )
            result = {"documentId": doc.id, "docCode": doc.doc_code, "version": doc.version, "origin": r.origin}
        sp.commit()
    except (IngestError, DocumentError, ValueError) as exc:
        sp.rollback()
        r.status, r.result = "failed", {"error": str(exc)[:500]}
        r.reviewed_by, r.reviewed_at, r.review_note = actor.emp_no, utcnow(), body.note
        audit(session, actor.emp_no, "db.upload.failed", "upload_request", str(r.id), {"error": str(exc)[:300], "via": via}, ip)
        session.commit()
        raise HTTPException(422, f"반영하지 못했습니다 — {exc}") from exc
    r.status, r.result = "approved", {**result, "via": via}
    r.reviewed_by, r.reviewed_at, r.review_note = actor.emp_no, utcnow(), body.note
    audit(session, actor.emp_no, "db.upload.approve", "upload_request", str(r.id), {"kind": r.kind, "target": r.target, "requestedBy": r.requested_by, "note": body.note, "via": via}, ip)
    audit(session, actor.emp_no, "db.upload.applied", "upload_request", str(r.id), result, ip)
    session.commit()
    if r.kind == "dataset":
        # 설명 카드를 바로 맞춘다(임베딩은 워커 주기 작업) — 실패해도 반영은 끝났고 다음 주기에 다시 맞춘다 (DOB-07)
        try:
            from nhdip.data.catalog import index_dataset_cards

            index_dataset_cards(session, [r.target])
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
    return _req_json(r, full=True)


def do_reject(session: Session, r: UploadRequest, actor: AppUser, body: ReviewIn, ip: str | None, via: str) -> dict[str, Any]:
    note = (body.note or "").strip()
    if not note:
        raise HTTPException(422, "반려 사유를 적어 주세요")
    r.status = "rejected"
    r.reviewed_by, r.reviewed_at, r.review_note = actor.emp_no, utcnow(), note[:1000]
    audit(session, actor.emp_no, "db.upload.reject", "upload_request", str(r.id), {"kind": r.kind, "target": r.target, "requestedBy": r.requested_by, "note": note[:300], "via": via}, ip)
    session.commit()
    return _req_json(r, full=True)


# ── 관리자 — 전체 요청 ──
@admin_router.get("/uploads")
def admin_uploads(status: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    q = select(UploadRequest).order_by(UploadRequest.id.desc()).limit(min(max(limit, 1), 300))
    if status:
        q = q.where(UploadRequest.status == status)
    return {"items": _list(session, q), "counts": _counts(session)}


@admin_router.post("/uploads/{rid}/approve")
def approve_upload(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    return do_approve(session, _pending(session, rid), admin, body, client_ip(request), "admin")


@admin_router.post("/uploads/{rid}/reject")
def reject_upload(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), admin: AppUser = Depends(require_admin)):
    if not (body.note or "").strip():
        raise HTTPException(422, "반려 사유를 적어 주세요")
    return do_reject(session, _pending(session, rid), admin, body, client_ip(request), "admin")


# ── 부서 데이터 책임자 — 자기 부서 사용자의 요청만 · 본인 요청은 다른 책임자 · 관리자가 (UPL-04 · Q107) ──
def _steward(user: AppUser = Depends(current_user)) -> AppUser:
    if not user.data_steward:
        raise HTTPException(403, "부서 데이터 책임자만 볼 수 있습니다 — 관리자 [사용자]에서 지정")
    return user


def _scope_orgs(session: Session, steward: AppUser) -> tuple[OrgUnit | None, set[str]]:
    """책임자 부서와 그 아래 조직 코드 전체 — 데이터 책임자 승인함(§40 STW)과 같은 기준."""
    from nhdip.stewardship import scope_orgs

    return scope_orgs(session, steward)


@router.get("/db/uploads/review")
def steward_review(status: str | None = "pending", session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    scope, orgs = _scope_orgs(session, user)
    where = UploadRequest.requested_org.in_(orgs or {"-"})
    q = select(UploadRequest).where(where).order_by(UploadRequest.id.desc()).limit(100)
    if status:
        q = q.where(UploadRequest.status == status)
    items = _list(session, q)
    for it in items:
        it["canReview"] = it["status"] == "pending" and it["requestedBy"] != user.emp_no
    return {"scope": {"code": scope.code, "name": scope.name} if scope else None, "items": items, "counts": _counts(session, where)}


def _steward_pending(session: Session, rid: int, user: AppUser) -> UploadRequest:
    from nhdip.orgs import in_steward_scope

    r = _pending(session, rid)
    if not in_steward_scope(session, user, r.requested_org):
        raise HTTPException(404, "요청 없음")  # 다른 부서 요청은 없는 것처럼
    if r.requested_by == user.emp_no:
        raise HTTPException(409, "본인이 올린 자료는 다른 책임자나 관리자가 승인해야 합니다")
    return r


@router.post("/db/uploads/{rid}/approve")
def steward_approve(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    return do_approve(session, _steward_pending(session, rid, user), user, body, client_ip(request), "steward")


@router.post("/db/uploads/{rid}/reject")
def steward_reject(rid: int, body: ReviewIn, request: Request, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    if not (body.note or "").strip():
        raise HTTPException(422, "반려 사유를 적어 주세요")
    return do_reject(session, _steward_pending(session, rid, user), user, body, client_ip(request), "steward")


def steward_pending_count(session: Session, user: AppUser) -> int:
    """사이드바 건수 — 책임자 부서의 승인 대기(본인 요청 제외)."""
    if not getattr(user, "data_steward", False):
        return 0
    _, orgs = _scope_orgs(session, user)
    if not orgs:
        return 0
    from sqlalchemy import func

    return int(session.execute(select(func.count()).select_from(UploadRequest).where(UploadRequest.status == "pending", UploadRequest.requested_org.in_(orgs), UploadRequest.requested_by != user.emp_no)).scalar() or 0)


# ── 부서 데이터 책임자 — 자기 부서가 올린 자료 삭제 (Phase J 후속 · DEL-09~12 · Q157~Q159) ──
# 소유는 자료를 만든 승인된 요청(requested_org)으로 판정한다. 다른 부서 자료는 없는 것처럼 404, 관리자 직접 업로드 자료는 요청이 없어 목록에 없다.
class StewardDeleteIn(BaseModel):
    reason: str
    all_versions: bool = False


def _owned_request(session: Session, rid: int, user: AppUser, *, lock: bool = False) -> UploadRequest:
    from nhdip.data.deletion import owned_by

    _, orgs = _scope_orgs(session, user)
    r = session.get(UploadRequest, rid, with_for_update=True if lock else None)
    if r is None or r.status != "approved" or r.kind not in ("dataset", "document") or r.requested_org not in orgs:
        raise HTTPException(404, "자료 없음")  # 다른 부서 · 반영 안 된 요청은 없는 것처럼
    if not owned_by(session, r, orgs):
        raise HTTPException(403, "같은 자료를 다른 부서도 올려 이 부서만으로는 지울 수 없습니다 — 데이터 관리자에게 요청하세요")
    return r


def _delete_http(exc: Exception) -> HTTPException:
    from nhdip.data.deletion import NotOwned

    msg = str(exc)
    if isinstance(exc, NotOwned):
        return HTTPException(403, msg)
    return HTTPException(404 if "없음" in msg else 409 if ("이미" in msg or "없습니다" in msg) else 422, msg)


@router.get("/db/steward/items")
def steward_items(deleted: bool = False, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    """우리 부서가 올려 반영된 자료 — 지울 수 있는 것(기본) 또는 지운 기록(deleted=true)."""
    from nhdip.data.deletion import steward_items as items_of

    scope, orgs = _scope_orgs(session, user)
    items = items_of(session, orgs, deleted=deleted)
    names = _names(session, {i["requestedBy"] for i in items} | {i["approvedBy"] for i in items if i.get("approvedBy")} | {(i.get("deleted") or {}).get("by") for i in items if i.get("deleted")} - {None})
    for i in items:
        i["requestedByName"] = names.get(i["requestedBy"])
        i["approvedByName"] = names.get(i.get("approvedBy") or "")
        if i.get("deleted"):
            i["deleted"] = {**i["deleted"], "byName": names.get((i["deleted"] or {}).get("by") or "")}
    return {"scope": {"code": scope.code, "name": scope.name} if scope else None, "items": items}


@router.get("/db/steward/items/{rid}/delete-preview")
def steward_delete_preview(rid: int, all_versions: bool = False, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    """삭제 전 확인 — 현재 자료인지, 무엇이 현재가 되는지, 지워지는 양, 다시 도는 워크플로우."""
    from nhdip.data.deletion import DeleteError, assert_owned_document_versions, preview_by_request, subject_id

    from .admin_data import _matched

    r = _owned_request(session, rid, user)
    try:
        if all_versions and r.kind == "document":
            _, orgs = _scope_orgs(session, user)
            assert_owned_document_versions(session, r.origin, subject_id(r) or 0, orgs)
        out, event, payload = preview_by_request(session, r, all_versions)
    except DeleteError as exc:  # NotOwned 도 DeleteError 의 하위
        raise _delete_http(exc) from exc
    out["workflows"] = _matched(session, event, payload) if out.get("isCurrent") else []
    out["requestId"] = r.id
    return out


@router.post("/db/steward/items/{rid}/delete")
def steward_delete(rid: int, body: StewardDeleteIn, request: Request, background: BackgroundTasks, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    """우리 부서 자료 삭제 — 관리자 삭제와 같은 연쇄(행 · 청크 · 색인 · 그래프 · 원본 · 재계산). 사유 필수."""
    from nhdip.data.deletion import DeleteError, assert_owned_document_versions, delete_by_request, subject_id

    from .admin_data import _after_delete

    r = _owned_request(session, rid, user, lock=True)
    try:
        if body.all_versions and r.kind == "document":
            _, orgs = _scope_orgs(session, user)
            assert_owned_document_versions(session, r.origin, subject_id(r) or 0, orgs)
        res = delete_by_request(session, r, user.emp_no, body.reason, client_ip(request), all_versions=body.all_versions)
    except DeleteError as exc:
        session.rollback()
        raise _delete_http(exc) from exc
    session.commit()
    _after_delete(background, res)
    return res.as_dict()


@router.get("/db/steward/purge-status")
def steward_purge_status(limit: int = 30, session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    """내가 지운 자료의 외부 저장소(Elasticsearch · Neo4j) 반영 상태."""
    from nhdip.data.deletion import purge_status

    return purge_status(session, limit, created_by=user.emp_no)


@router.post("/db/steward/purge-run")
def steward_purge_run(session: Session = Depends(get_session), user: AppUser = Depends(_steward)):
    """내가 낸 삭제 작업 중 대기 중인 것을 바로 다시 실행한다."""
    from nhdip.data.deletion import pending_purge_ids, run_purge_tasks

    ids = pending_purge_ids(session, user.emp_no)
    return run_purge_tasks(session, ids=ids) if ids else {"done": 0, "skipped": 0, "pending": 0}


# ═════════════════════════ 자료 등록(온보딩) — 분석 → 확인 · 고침 → 반영 / 승인 요청 (Phase M · 요구사항 §31 · Q191~Q197) ═════════════════════════
# 등록 건은 요청 표(ops.upload_request)에 '초안(draft)'으로 남는다(Q197) — 반영하면 기존 승인 경로(do_approve)를 그대로 타서
# 소유(Q157 · 우리 부서 자료 삭제) · 감사 · 품질 검사 · 이벤트가 같다. 같은 API 를 업무 [자료 올리기]와 관리자 [데이터셋 · 문서]가 쓴다(Q191).
class IntakePatch(BaseModel):
    definition: dict[str, Any] | None = None  # 새 자료의 정의(코드 · 이름 · 설명 · 열 라벨 · 키 · 기준일 열 등)
    document: dict[str, Any] | None = None  # 문서 정보 {title, doc_class, issuer, published_at, origin}
    target: str | None = None  # 기존 자료로 올릴 때 다른 데이터셋을 고름
    asOf: str | None = None
    note: str | None = None


def _self_apply(session: Session, user: AppUser) -> str | None:
    """바로 반영할 수 있으면 감사 경로(via), 아니면 None(승인 요청). 관리자 · 데이터 관리자 · 자기 부서 책임자(설정이 허용할 때)."""
    if user.role == "admin" or getattr(user, "data_admin", False):
        return "admin"
    if getattr(user, "data_steward", False):
        from nhdip.orgs import steward_scope

        st = session.get(Setting, "intake.steward_self_apply")
        if (st is None or st.value is not False) and steward_scope(session, user.org_code) is not None:
            return "steward-self"
    return None


def _intake(session: Session, rid: int, user: AppUser, lock: bool = False) -> UploadRequest:
    r = session.get(UploadRequest, rid, with_for_update=lock)
    if r is None or (r.requested_by != user.emp_no and user.role != "admin"):
        raise HTTPException(404, "등록 건 없음")  # 다른 사람의 등록 건은 없는 것처럼
    return r


def _intake_json(session: Session, r: UploadRequest, user: AppUser) -> dict[str, Any]:
    from nhdip.data.onboarding import storage_status

    out = _req_json(r, full=True)
    out["intake"] = (r.meta or {}).get("intake") or {}
    out["canApply"] = r.status == "draft" and _self_apply(session, user) is not None
    out["applyMode"] = "apply" if _self_apply(session, user) else "request"
    out["storage"] = storage_status(session, r)
    return out


@router.post("/db/intake", status_code=201)
async def intake_create(
    request: Request,
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    title: str | None = Form(None),
    origin: str = Form("bank"),
    user: AppUser = Depends(require_resource("db_upload")),
    session: Session = Depends(get_session),
):
    """파일(또는 붙여 넣은 본문) → 정형/비정형 판별 → 에이전트 분석 → 초안 등록 건(아직 아무 데이터도 반영하지 않음)."""
    from nhdip.data.onboarding import analyze_document, analyze_structured, is_structured

    if origin not in ("bank", "ext"):
        raise HTTPException(422, "origin 은 bank(당행) | ext(외부)")
    if file is not None and file.filename:
        purpose = "dataset" if is_structured(file.filename) or file.filename.lower().endswith(".md") else "document"
        name, content = await read_upload(file, purpose, session, request, user.emp_no)
        if name.lower().endswith(".md"):
            # 마크다운은 내용으로 — 표가 있으면 정형 자료, 없으면 문서 (Phase Q · MD-03)
            purpose = "dataset" if is_structured(name, content) else "document"
    elif (text or "").strip():
        purpose = "document"
        name, content = f"{re.sub(r'[^0-9A-Za-z가-힣]+', '_', title or '붙여넣은_본문')[:60]}.txt", (text or "").encode("utf-8")
    else:
        raise HTTPException(422, "파일이나 본문을 넣어 주세요")
    try:
        if purpose == "dataset":
            an = analyze_structured(session, name, content, origin=origin)
        else:
            an = analyze_document(session, name, content)
            if title and title.strip():
                an["document"]["title"] = title.strip()[:200]
    except (IngestError, DocumentError, ValueError) as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from exc
    sha, path = _store(user.emp_no, name, content)
    if purpose == "dataset":
        d = an.get("definition") or {}
        meta = {"intake": an, "targetLabel": an.get("targetName") or d.get("name") or an.get("target"), "dataOrigin": "actual", **({"proposal": d} if an["mode"] == "new" else {})}
        kind, target, org = "dataset", str(an.get("target") or ""), str(an.get("origin") or origin)
        preview = {"rows": an.get("rows"), "quality": (an.get("quality") or {}).get("status"), "mode": an["mode"]}
    else:
        doc = an["document"]
        meta = {"intake": an, "targetLabel": next((c["label"] for c in an.get("classes") or [] if c["code"] == doc["doc_class"]), doc["doc_class"]), "title": doc["title"],
                "issuer": doc.get("issuer"), "publishedAt": doc.get("published_at")}
        kind, target, org = "document", str(doc["doc_class"]), str(doc.get("origin") or "bank")
        preview = {"chars": an.get("chars"), "pages": an.get("pages"), "excerpt": an.get("excerpt")}
    r = UploadRequest(kind=kind, target=target[:60], origin=org, file_name=name, file_path=path, file_sha256=sha, meta=meta, preview=preview, status="draft", requested_by=user.emp_no, requested_org=user.org_code)
    session.add(r)
    session.flush()
    audit(session, user.emp_no, "db.intake.create", "upload_request", str(r.id), {"kind": kind, "mode": an.get("mode"), "target": target, "file": name, "llm": (an.get("llm") or {}).get("by")}, client_ip(request))
    session.commit()
    return _intake_json(session, r, user)


@router.get("/db/intake/mine")
def intake_mine(user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    rows = session.execute(select(UploadRequest).where(UploadRequest.requested_by == user.emp_no, UploadRequest.meta["intake"].astext.is_not(None)).order_by(UploadRequest.id.desc()).limit(30)).scalars().all()
    return {"items": [{**_req_json(r), "mode": ((r.meta or {}).get("intake") or {}).get("mode")} for r in rows], "applyMode": "apply" if _self_apply(session, user) else "request"}


@router.get("/db/intake/{rid}")
def intake_get(rid: int, user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    return _intake_json(session, _intake(session, rid, user), user)


@router.patch("/db/intake/{rid}")
def intake_patch(rid: int, body: IntakePatch, request: Request, user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    """초안 고치기 — 정의(새 자료) · 문서 정보 · 기존 자료 대상 · 기준일. 고친 정의는 저장 전 점검한다."""
    r = _intake(session, rid, user, lock=True)
    if r.status != "draft":
        raise HTTPException(409, f"초안이 아닙니다({STATUS_LABEL.get(r.status, r.status)})")
    meta = dict(r.meta or {})
    if body.definition is not None and r.kind == "dataset":
        d = {k: body.definition[k] for k in PROPOSAL_FIELDS if k in body.definition}
        problems = validate_definition(d)
        if problems:
            raise HTTPException(422, " · ".join(problems[:6]))
        if d["code"] != r.target and session.get(Dataset, d["code"]) is not None:
            raise HTTPException(409, f"이미 있는 데이터셋 코드입니다: {d['code']} — 다른 코드로 하거나 '기존 자료'로 올리세요")
        meta["proposal"], meta["targetLabel"] = d, d.get("name") or d["code"]
        r.target = d["code"][:60]
    if body.target is not None and r.kind == "dataset":
        ds = _dataset_for_user(session, body.target)
        meta.pop("proposal", None)
        meta["targetLabel"] = ds.name
        r.target, r.origin = ds.code, ds.origin
    if body.document is not None and r.kind == "document":
        doc = body.document
        classes = {c["key"] for c in _doc_classes(session, user)}
        if doc.get("doc_class") and doc["doc_class"] not in classes:
            raise HTTPException(422, "올릴 수 없는 문서 분류입니다")
        if doc.get("published_at") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(doc["published_at"])):
            raise HTTPException(422, "시행일은 YYYY-MM-DD 형식입니다")
        title = str(doc.get("title") or meta.get("title") or "").strip()
        if not title or len(title) > 200:
            raise HTTPException(422, "제목은 1~200자입니다")
        meta.update(title=title, issuer=(doc.get("issuer") or None), publishedAt=(doc.get("published_at") or None))
        if doc.get("doc_class"):
            r.target = doc["doc_class"]
        if doc.get("origin") in ("bank", "ext"):
            r.origin = doc["origin"]
    if body.asOf is not None:
        if body.asOf and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.asOf):
            raise HTTPException(422, "기준일은 YYYY-MM-DD 형식입니다")
        meta["asOf"] = body.asOf or None
    if body.note is not None:
        meta["note"] = body.note[:500]
    r.meta = meta
    audit(session, user.emp_no, "db.intake.update", "upload_request", str(r.id), {"target": r.target}, client_ip(request))
    session.commit()
    return _intake_json(session, r, user)


@router.post("/db/intake/{rid}/submit")
def intake_submit(rid: int, body: ReviewIn, request: Request, user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    """확인 끝 — 책임자(자기 부서) · 데이터 관리자 · 관리자는 바로 반영, 그 밖의 사용자는 승인 요청(기존 승인 대기)으로."""
    r = _intake(session, rid, user, lock=True)
    if r.status != "draft":
        raise HTTPException(409, f"초안이 아닙니다({STATUS_LABEL.get(r.status, r.status)})")
    if r.kind == "dataset" and (r.meta or {}).get("proposal") is None and session.get(Dataset, r.target) is None:
        raise HTTPException(422, "올릴 데이터셋을 정하세요(기존 자료를 고르거나 새 자료 정의를 확인)")
    if r.kind == "dataset" and (r.meta or {}).get("proposal") is not None and _pending_proposal(session, r.target):
        raise HTTPException(409, "같은 코드의 새 자료 요청이 이미 승인 대기 중입니다")
    if r.kind == "dataset":
        _no_common(user, dataset=session.get(Dataset, r.target))
    else:
        _no_common(user, doc_class=r.target, session=session)
    via = _self_apply(session, user)
    r.status = "pending"
    if via is None:
        audit(session, user.emp_no, "db.upload.request", "upload_request", str(r.id), {"kind": r.kind, "target": r.target, "via": "intake"}, client_ip(request))
        session.commit()
        return _intake_json(session, r, user)
    session.flush()
    do_approve(session, r, user, body, client_ip(request), via)
    return _intake_json(session, session.get(UploadRequest, rid), user)


@router.post("/db/intake/{rid}/discard")
def intake_discard(rid: int, request: Request, user: AppUser = Depends(require_resource("db_upload")), session: Session = Depends(get_session)):
    r = _intake(session, rid, user, lock=True)
    if r.status != "draft":
        raise HTTPException(409, "초안만 버릴 수 있습니다")
    r.status = "discarded"
    try:
        if r.file_path and os.path.exists(r.file_path):
            os.remove(r.file_path)  # 반영하지 않은 파일은 남기지 않는다
    except OSError:
        pass
    audit(session, user.emp_no, "db.intake.discard", "upload_request", str(r.id), None, client_ip(request))
    session.commit()
    return {"ok": True}
