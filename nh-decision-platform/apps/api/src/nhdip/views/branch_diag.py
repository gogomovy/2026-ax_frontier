"""영업점 화면이 비어 있을 때 — 왜 그 지점이 계산되지 않았는지 단계별로 짚는다.

지점 화면(branch_dashboard@지점)은 영업점 흐름(wf_branch_kpi)의 지점별 범위 실행이 만든다. 범위가 되려면
  1) 조직표에 그 영업점이 있고(사무소 코드 매핑 포함)
  2) 범위 설정의 필요한 자료(사무소 마스터 · 득점 현황 등)마다 그 지점 행이 있어야 하며(그 자료가 업무 구성이 읽는 정의에 있어야)
  3) 흐름이 그 뒤에 돌아(대기 · 실행 중이 아니고) 그 지점 범위를 건너뛰지 않았어야
  4) 산출물이 그 지점 것으로 게시되고 자료로 계산돼 있어야 한다.
여기서는 새 값을 만들지 않고 지금 상태만 읽는다.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def diagnose(session: Session, office: str) -> dict[str, Any]:
    from nhdip.data.datasets import current_rows, current_versions
    from nhdip.data.sources import Resolver
    from nhdip.models import Dataset, Job, WorkflowRun, source
    from nhdip.orgs import office_code_of, org_of_office
    from nhdip.scopes import _req_pair, computed_offices, office_scope, scope_specs, scoped_key
    from nhdip.views.readiness import computed
    from nhdip.views.store import get_current

    steps: list[dict[str, Any]] = []

    def step(key: str, ok: bool, detail: str, **extra: Any) -> None:
        steps.append({"key": key, "ok": ok, "detail": detail, **extra})

    org = org_of_office(session, office)
    step("org", org is not None and org.unit_type == "BRANCH" and org.active,
         f"조직표 {org.name}({org.code}) · {org.unit_type}{'' if org.active else ' · 사용 안 함'}" if org else f"조직표에 사무소 코드 {office} 인 영업점이 없습니다 — [조직 관리] 또는 설정 branch.office_codes")
    spec = next(((wf, sp) for wf, sp in scope_specs(session).items() if sp.get("name") == "office"), None)
    if spec is None:
        step("scope", False, "영업점 범위 설정(workflow.scopes 의 office)이 없습니다")
        return {"office": office, "steps": steps, "verdict": steps[-1]["detail"]}
    wf, sp = spec
    res = Resolver(session)
    for req in sp.get("requires") or []:
        name, col = _req_pair(req)
        d = res.resolve(name)
        if d is None:
            step(f"requires:{name}", False, f"'{name}' 자료가 아직 없습니다(업무 구성이 읽을 정의 · 올린 판 없음)")
            continue
        real = res.aliases(name, d).get(col, col)
        _, rows = current_rows(session, d)
        mine = sum(1 for r in rows if str(r.get(real)) == office)
        others = sorted({str(r.get(real)) for r in rows if r.get(real) not in (None, "")})[:12]
        # 같은 모양인데 업무 구성이 읽지 않는 정의에 이 지점 행이 있는지(갈라진 정의)
        shadow = []
        for x in res.candidates(res.spec(name)) if res.spec(name) else []:
            if x.code == d.code:
                continue
            _, xr = current_rows(session, x)
            if any(str(r.get(real)) == office for r in xr):
                shadow.append(x.code)
        detail = f"'{name}'({d.code}) 의 {real} 열에 {office} 행 {mine}개" + ("" if mine else f" — 지금 있는 지점: {', '.join(others) or '없음'}")
        if shadow:
            detail += f" · 업무 구성이 읽지 않는 정의 {', '.join(shadow)} 에 이 지점 행이 있습니다 — [데이터셋·문서]의 [한 정의로 모으기]"
        owners = sorted({str(v.owner_org) for v in current_versions(session, d)})
        step(f"requires:{name}", mine > 0, detail, dataset=d.code, owners=owners)
    primary, offices = office_scope(session)
    step("scope", office in offices or office == primary,
         f"계산 대상 지점: {', '.join(offices[:20])}" + ("" if office in offices else f" — {office} 없음(필요한 자료 · 상한 max {sp.get('max', 20)})"))
    pending = session.execute(select(Job).where(Job.workflow_code == wf, Job.status.in_(("queued", "running")))).scalars().all()
    run = session.execute(select(WorkflowRun).where(WorkflowRun.workflow_code == wf).order_by(WorkflowRun.started_at.desc()).limit(1)).scalars().first()
    if pending:
        step("run", False, f"{wf} 이 {'실행 중' if any(j.status == 'running' for j in pending) else '대기 중'}입니다 — 끝나면 다시 보세요", jobs=len(pending))
    elif run is None:
        step("run", False, f"{wf} 이 아직 한 번도 돌지 않았습니다 — 워커(worker) 상태를 확인하세요")
    else:
        summ = run.summary or {}
        mine = next((x for x in summ.get("scopes") or [] if str(x.get("value")) == office), None)
        if office == primary:
            ok, why = run.status in ("succeeded", "degraded"), f"기본 지점 · 최근 실행 {run.status}"
        elif mine is None:
            dropped = office in (summ.get("scopes_dropped") or [])
            ok, why = False, f"최근 실행({run.status} · {run.started_at:%m-%d %H:%M})에 {office} 범위가 없습니다" + (" — 범위 상한(max)에 걸려 빠졌습니다" if dropped else " — 그 뒤 자료가 바뀌었으면 다시 실행되기를 기다리거나 [실행 현황]에서 다시 실행")
        else:
            ok = mine.get("status") in ("succeeded", "degraded")
            why = f"최근 실행 {office} 범위: {mine.get('status')}" + (f" — {mine.get('reason') or mine.get('error')}" if not ok else "")
        step("run", ok, why, run=run.id, status=run.status, error=(run.error or "")[:300] or None)
    v = get_current(session, scoped_key("branch_dashboard", office, primary))
    if not isinstance(v, dict):
        step("artifact", False, "지점 화면 산출물이 아직 게시되지 않았습니다")
    else:
        code = str((v.get("office") or {}).get("code") or "")
        step("artifact", code == office and computed(v), f"게시된 산출물 지점 {code or '-'} · {'자료로 계산됨' if computed(v) else '값 없는 틀'}")
    step("computed", office in computed_offices(session), "지점 목록 · 영업본부 통합에 계산된 지점으로 나옵니다" if office in computed_offices(session) else "계산된 지점 목록에 없습니다")
    first = next((s for s in steps if not s["ok"]), None)
    # 그 지점 소유 판이 올라간 자료(참고)
    owned = []
    if org is not None:
        for o in ("bank", "ext"):
            t = source(o)
            owned += sorted({c for c in session.execute(select(t.version.dataset_code).where(t.version.is_current, t.version.owner_org == org.code)).scalars()})
        names = {d.code: d.name for d in session.execute(select(Dataset).where(Dataset.code.in_(owned))).scalars()} if owned else {}
        owned = [{"code": c, "name": names.get(c, c)} for c in owned]
    return {"office": office, "org": office_code_of(session, org.code) if org else None, "ok": first is None, "steps": steps, "ownedDatasets": owned,
            "verdict": first["detail"] if first else "정상 — 지점 화면이 계산돼 있습니다"}
