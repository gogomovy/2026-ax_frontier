"""같은 자료가 여러 정의로 갈라진 것 정리 — 업무 구성이 읽는 정의 하나로 판을 모은다.

생기는 경우: 여러 파일을 한꺼번에 [자료 등록]하면 분석 때는 아직 정의가 없어 파일마다 새 정의(…_2 · …_3)가 제안되고, 승인하면 그대로 만들어졌다.
업무 구성은 자료 이름마다 정의 하나만 읽으므로(Resolver) 나머지 정의에 들어간 영업점 · 기간 자료가 화면에 나오지 않는다.
(반영 때 다시 맞추도록 고쳤으므로 앞으로는 생기지 않는다 — 이미 갈라진 자료를 한 번 정리한다.)

  plan(session)            무엇을 어디로 모을지(미리보기)
  execute(session, actor)  갈라진 정의의 현재 판을 대상 정의의 새 판으로 다시 올리고(소유 · 기준일 · 파일 정보 그대로, 영업점 행이면 그 영업점 판),
                           갈라진 정의는 사용 중지(판 · 행은 이력으로 남는다). 대상 정의에서 팀 소유로 잘못 들어간 영업점 판은 그 영업점 소유로 바로잡는다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, source

from .sources import Resolver, norm


def _colset(d: Dataset) -> set[str]:
    return {norm(c.get("name")) for c in d.columns or [] if c.get("name")}


def plan(session: Session) -> list[dict[str, Any]]:
    res = Resolver(session)
    out: list[dict[str, Any]] = []
    used: set[str] = set()
    for sp in res.specs.values():
        target = res.resolve(sp.name)
        if target is None or target.code in used or getattr(target, "common", False):
            continue
        used.add(target.code)
        dups = [d for d in res.candidates(sp) if d.code != target.code and d.origin == target.origin and not getattr(d, "common", False) and _colset(d) == _colset(target)]
        if not dups:
            continue
        t = source(target.origin)
        items = []
        for d in dups:
            vs = session.execute(select(t.version).where(t.version.dataset_code == d.code, t.version.is_current, t.version.status == "committed").order_by(t.version.committed_at)).scalars().all()
            items.append({"code": d.code, "name": d.name, "versions": [{"version": v.version, "asOf": v.as_of.isoformat() if v.as_of else None, "owner": v.owner_org, "file": v.file_name, "rows": v.row_count} for v in vs]})
        out.append({"source": sp.name, "target": {"code": target.code, "name": target.name}, "duplicates": items})
    return out


def _fix_target_owners(session: Session, ds: Dataset, actor: str) -> list[dict[str, Any]]:
    """대상 정의의 현재 판 가운데 팀 · 전행 소유인데 행이 모두 한 영업점 것인 판 — 그 영업점 소유로(이미 그 영업점 판이 있으면 내린다)."""
    from nhdip.orgs import is_branch

    from .datasets import change_version_owner, partition_clause
    from .placement import content_branches

    t = source(ds.origin)
    fixed = []
    for v in session.execute(select(t.version).where(t.version.dataset_code == ds.code, t.version.is_current).order_by(t.version.committed_at)).scalars().all():
        if is_branch(session, v.owner_org):
            continue
        rows = session.execute(select(t.row.data).where(t.row.version_id == v.id)).scalars().all()
        got = content_branches(session, ds, rows)
        if len(got) != 1:
            continue
        clash = session.execute(select(t.version.id).where(t.version.dataset_code == ds.code, t.version.is_current, t.version.id != v.id,
                                                          partition_clause(session, t, v.as_of, got[0])).limit(1)).first()
        if clash:
            v.is_current = False
            fixed.append({"version": v.version, "action": "retired", "branch": got[0]})
        else:
            change_version_owner(session, ds, v.id, got[0], actor)
            fixed.append({"version": v.version, "action": "owner", "from": v.owner_org, "branch": got[0]})
    return fixed


def execute(session: Session, actor: str) -> list[dict[str, Any]]:
    from nhdip.events import audit

    from nhdip.orgs import is_branch

    from .datasets import branch_owner_from_rows, ingest_rows, quality_check
    from .placement import content_branches

    out = []
    done: set[str] = set()
    for p in plan(session):
        target = session.get(Dataset, p["target"]["code"])
        t = source(target.origin)
        moved = []
        for dup in p["duplicates"]:
            d = session.get(Dataset, dup["code"])
            vs = session.execute(select(t.version).where(t.version.dataset_code == d.code, t.version.is_current, t.version.status == "committed").order_by(t.version.committed_at)).scalars().all()
            for v in vs:
                rows = [{k: val for k, val in r.items() if not str(k).startswith("__")}
                        for r in session.execute(select(t.row.data).where(t.row.version_id == v.id).order_by(t.row.row_no)).scalars()]
                got = content_branches(session, target, rows)
                # 행이 한 영업점 것이면 그 영업점 판, 영업점 소유인데 행이 다른 영업점 · 여러 영업점이면 전행 공통(다른 영업점 판을 밀어내지 않게)
                owner = got[0] if len(got) == 1 else (None if is_branch(session, v.owner_org) and got else branch_owner_from_rows(session, target, rows, v.owner_org, "*"))
                nv = ingest_rows(session, target, rows, quality=quality_check(target, rows, []), file_name=v.file_name, file_sha=v.file_sha256, file_path=v.file_path,
                                 as_of=v.as_of.isoformat() if v.as_of else None, data_origin=v.data_origin, actor=actor, note=f"정의 정리 — {d.code} v{v.version} 에서 옮김",
                                 force=True, owner_org=owner, memo=getattr(v, "memo", None), requested_by=getattr(v, "requested_by", None) or v.uploaded_by)
                v.is_current = False
                moved.append({"from": f"{d.code} v{v.version}", "to": f"{target.code} v{nv.version}", "owner": owner, "asOf": v.as_of.isoformat() if v.as_of else None})
            d.active = False
        session.flush()
        fixed = _fix_target_owners(session, target, actor)
        done.add(target.code)
        audit(session, actor, "dataset.consolidate", "dataset", target.code, {"duplicates": [x["code"] for x in p["duplicates"]], "moved": moved, "ownerFixed": fixed})
        out.append({**p, "moved": moved, "ownerFixed": fixed})
    # 갈라진 정의가 없어도 — 업무 구성이 읽는 정의에 팀 · 관리자 소유로 들어간 영업점 판을 그 영업점 판으로
    res = Resolver(session)
    for sp in res.specs.values():
        target = res.resolve(sp.name)
        if target is None or target.code in done or getattr(target, "common", False):
            continue
        done.add(target.code)
        fixed = _fix_target_owners(session, target, actor)
        if fixed:
            audit(session, actor, "dataset.consolidate", "dataset", target.code, {"duplicates": [], "moved": [], "ownerFixed": fixed})
            out.append({"source": sp.name, "target": {"code": target.code, "name": target.name}, "duplicates": [], "moved": [], "ownerFixed": fixed})
    return out
