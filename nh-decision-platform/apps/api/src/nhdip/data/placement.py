"""반영 미리보기 (Phase P · UPV-01~05) — 이 파일이 같은 자료의 어느 판으로 들어가는지 요청 때 알려 준다.

판 구분 = 기준일 × 소유 구획(영업점은 영업점마다, 그 밖은 기준일 하나에 현재 판 하나 — `partition_clause`).
- 기준일이 다르면 '새 기준일로 추가'(날짜별로 함께 보관 · 날짜별 비교 가능), 같으면 '같은 기준일 판 교체'
- 메모는 설명일 뿐 판을 구분하지 않는다. 시행일은 문서 전용
- 기준일 열이 있는 자료에서 입력 기준일의 달이 파일 기간에 없으면 거절(다른 달 판을 잘못 교체하지 않게)
- 같은 구획 현재 판과 같은 파일이면 경고(반영해도 다시 계산하지 않음)
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, OrgUnit, source

from .datasets import partition_clause, to_date


def _ym(iso: str | None) -> str | None:
    return iso[:7] if iso else None


_CODE_TOKEN = re.compile(r"[A-Za-z]{0,4}\d{3,6}")


def _org_label(session: Session, code: str | None) -> str:
    if not code:
        return "전행 공통"
    o = session.get(OrgUnit, code)
    return f"{o.name}({code})" if o is not None else code


def file_owner_hint(session: Session, file_name: str | None) -> str | None:
    """파일 이름 안의 영업점 코드(예: Oblg_grd_def_202608_BR302.csv → BR302) — 조직표에 있는 영업점일 때만. 기준월 같은 숫자는 조직이 아니면 무시."""
    if not file_name:
        return None
    stem = re.sub(r"\.[^.]+$", "", file_name)
    for tok in re.split(r"[_\-\s()\[\]·.]+", stem):
        if tok and _CODE_TOKEN.fullmatch(tok):
            o = session.get(OrgUnit, tok.upper()) or session.get(OrgUnit, tok)
            if o is not None and o.active and o.unit_type == "BRANCH":
                return o.code
    return None


def placement(session: Session, ds: Dataset, rows: list[dict[str, Any]], *, as_of: str | None, owner_org: str | None, file_sha: str | None = None, file_name: str | None = None) -> dict[str, Any]:
    from nhdip.orgs import is_branch

    from .datasets import current_versions

    if getattr(ds, "common", False):
        owner_org = None
    dates = sorted({d for d in (to_date(r.get(ds.as_of_column)) for r in rows if ds.as_of_column and r.get(ds.as_of_column) is not None) if d})
    version_as_of = as_of or (dates[-1] if dates else None)
    out: dict[str, Any] = {"typedAsOf": as_of or None, "versionAsOf": version_as_of, "fileFrom": dates[0] if dates else None, "fileTo": dates[-1] if dates else None, "fileDates": len(dates),
                           "asOfColumn": ds.as_of_column, "noAsOfColumn": not ds.as_of_column, "action": "add", "replaces": None, "overlaps": [], "duplicateOf": None, "existing": [], "messages": [], "error": None}
    if as_of and ds.as_of_column and dates and _ym(as_of) not in {_ym(d) for d in dates}:
        out["error"] = (f"입력한 기준일 {as_of} 의 달이 파일 기간({dates[0]} ~ {dates[-1]})에 없습니다 — 다른 기준일 판을 잘못 바꾸지 않도록 요청하지 않았습니다. "
                        "기준일을 비우면 파일 기간의 마지막 날로 들어갑니다")
    t = source(ds.origin)
    cur = current_versions(session, ds) if session.get(Dataset, ds.code) is not None else []
    out["existing"] = sorted([{"asOf": v.as_of.isoformat() if v.as_of else None, "version": v.version, "rows": v.row_count, "memo": getattr(v, "memo", None), "owner": v.owner_org,
                               "committedAt": v.committed_at.isoformat() if v.committed_at else None} for v in cur], key=lambda p: (p["asOf"] or "", p["version"]))[-24:]
    if cur:
        from datetime import date

        va = date.fromisoformat(version_as_of) if version_as_of else None
        same = session.execute(select(t.version).where(t.version.dataset_code == ds.code, t.version.is_current, partition_clause(session, t, va, owner_org))
                               .order_by(t.version.committed_at.desc())).scalars().all()
        if same:
            v = same[0]
            out["action"] = "replace"
            out["replaces"] = {"version": v.version, "asOf": v.as_of.isoformat() if v.as_of else None, "memo": getattr(v, "memo", None), "rows": v.row_count, "committedAt": v.committed_at.isoformat() if v.committed_at else None}
            twin = next((x for x in same if file_sha and x.file_sha256 == file_sha and x.row_count == len(rows)), None)
            if twin is not None:
                out["duplicateOf"] = {"version": twin.version}
        # 여러 기간이 든 파일 — 이미 다른 판에 있는 기간(최근 반영 판이 그 기간 행을 쓴다)
        if ds.as_of_column and len(dates) > 1:
            have: dict[str, int] = {}
            for v in cur:
                for d in session.execute(select(t.row.as_of).where(t.row.version_id == v.id).distinct()).scalars():
                    if d is not None:
                        have.setdefault(d.isoformat(), v.version)
            out["overlaps"] = [{"asOf": d, "version": have[d]} for d in dates if d in have and d != version_as_of][:24]
    # 소유 구획 — 영업점 자료는 영업점마다 현재 판을 따로 둔다(버전 번호는 자료 전체에서 이어 붙지만 다른 영업점 판을 바꾸지 않는다)
    branch = is_branch(session, owner_org)
    out["owner"] = {"code": owner_org, "label": _org_label(session, owner_org), "branch": branch}
    out["nextVersion"] = (session.execute(select(t.version.version).where(t.version.dataset_code == ds.code).order_by(t.version.version.desc()).limit(1)).scalar() or 0) + 1
    out["kept"] = [{"version": v.version, "asOf": v.as_of.isoformat() if v.as_of else None, "owner": v.owner_org, "ownerLabel": _org_label(session, v.owner_org)}
                   for v in cur if not (out["replaces"] and v.version == out["replaces"]["version"])][:24]
    hint = file_owner_hint(session, file_name)
    out["fileOwnerHint"] = {"code": hint, "label": _org_label(session, hint)} if hint else None
    out["ownerMismatch"] = bool(hint and hint != owner_org)
    m = out["messages"]
    who = out["owner"]["label"]
    if out["ownerMismatch"]:
        m.append(f"파일 이름에 {out['fileOwnerHint']['label']} 가 있는데 자료를 둘 곳이 {who} 입니다 — 맞는지 확인하세요.")
    if out["action"] == "add":
        if not cur:
            m.append(f"이 자료의 첫 판입니다({who}).")
        elif branch:
            m.append(f"{who} 자료로 새로 추가합니다(v{out['nextVersion']}) — 다른 영업점 · 전행 판 {len(cur)}개는 그대로 현재 판으로 남습니다.")
        else:
            m.append(f"새 기준일({version_as_of or '기준일 없음'})로 추가합니다(v{out['nextVersion']}) — 이미 있는 판 {len(cur)}개는 그대로 두고 함께 보관(날짜별 비교 가능).")
    else:
        r = out["replaces"]
        scope = f"{who}의 " if branch else ""
        m.append(f"{scope}같은 기준일({r['asOf'] or '기준일 없음'}) 현재 판 v{r['version']}" + (f"(메모: {r['memo']})" if r.get("memo") else "") + f"을 이 파일(v{out['nextVersion']})로 교체합니다 — 이전 판은 이력으로 남아 되돌릴 수 있습니다."
                 + (" 다른 영업점 판은 바뀌지 않습니다." if branch else ""))
    if out["overlaps"]:
        m.append(f"파일 안 {len(out['overlaps'])}개 기간은 이미 다른 판에 있습니다 — 반영하면 그 기간은 이 파일 값이 쓰입니다(최근 반영 우선).")
    if out["duplicateOf"]:
        m.append(f"같은 파일이 이미 현재 판(v{out['duplicateOf']['version']})입니다 — 반영해도 결과가 바뀌지 않아 다시 계산하지 않습니다.")
    if out["noAsOfColumn"]:
        m.append("이 자료에는 기준일 열이 없습니다 — 기준일을 적으면 날짜별로 보관되지만 계산은 가장 늦은 기준일 판만 씁니다. 날짜별 비교가 필요하면 파일에 기준일 열을 넣으세요.")
    m.append("메모는 판 설명으로만 남고 판을 구분하지 않습니다 — 같은 자료의 판은 기준일로 구분됩니다.")
    return out
