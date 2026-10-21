"""화면 설정 (Phase K · 요구사항 §27 HC-01~05 · SCP-01 · 설계 §27.1 · Q148~Q151).

화면 코드에 두던 판정 구간 · 기준값 · 목표 역할 · 업무 영역 · 예시 질문 · 알림 목록을 `cfg.setting` 의 `ui.*` 키로 둔다.
- 기본값(`DEFAULTS`)은 업무 값이 없는 틀 — 목표 역할 · 업무 영역 · 예시 질문 · 하위 영역 이름은 업무 구성 파일이 채운다(Phase O). 시드는 없는 키만 넣는다.
- `validate(key, value)` — 저장 전 형식 검사(관리자 [화면 설정] · `PUT /admin/settings/{key}`). 틀리면 `UiConfigError`(→ 422).
- `client_config(session, user, branch=...)` — `/me/menu.config` 로 내려 주는 값. 저장된 값이 깨져 있으면 기본값으로(화면이 멈추지 않게).
"""
from __future__ import annotations

import copy
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import OrgUnit, Screen, Setting

TONES = ("neutral", "info", "positive", "attention", "critical")
SCOPE_KINDS = ("hq", "dept", "branch")
GOAL_ROLES = {
    "bankRevenue": "은행 수익 목표(종합 현황 [여신 이자마진 수익] 카드)",
    "corpGrowth": "기업여신 성장 목표(목표 경로 · 분석 탭 표시)",
    "hhLimit": "가계여신 잔액 관리 한도(한도선 · 여유)",
    "hhControl": "가계여신 관리목표(분석 탭 표시)",
}
BAND_KEYS = {
    "limitUsage": "한도 소진율(%) — 은행 종합목표 총자산 한도 카드",
    "rwaUsage": "신용RWA 소진율(%) — 종합 현황 · 총자산 · 수익성 기준",
    "targetProgress": "본부 전파 목표 진행률(%) — 영업점 [본부 전파 목표 · 가이드]",
    "evidenceRelevance": "근거 문서 관련도(0~1) — 근거 원문 서랍",
}
THRESHOLD_KEYS = {
    "planPaceTolerancePp": ("계획 수준 허용 폭(%p) — 목표 진행률이 연간 경과율보다 이만큼 낮아도 '계획 수준'", 0, 100),
    "headroomAlert": ("한도 여유 경고 폭(한도와 같은 단위) — 남은 여유가 이보다 작으면 강조", 0, 1_000_000),
    "shareReferencePct": ("구성비 막대 기준선(%)", 0, 100),
    "proposalReasonMin": ("목표 제안 강제 반영 사유 최소 글자 수", 1, 200),
}
VERDICTS = ("breach", "below", "near_limit", "on_track")
COUNT_KEY = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{1,39}$")

_LIMIT_BANDS = [
    {"max": 85, "label": "정상", "tone": "neutral"},
    {"max": 100, "label": "한도 근접", "tone": "attention"},
    {"max": None, "label": "한도 초과", "tone": "critical"},
]

DEFAULTS: dict[str, tuple[Any, str]] = {
    "ui.bands": (
        {
            "limitUsage": _LIMIT_BANDS,
            "rwaUsage": _LIMIT_BANDS,
            "targetProgress": [{"max": 90, "label": "진행 중", "tone": "neutral"}, {"max": None, "label": "목표 근접", "tone": "attention"}],
            "evidenceRelevance": [
                {"max": 0.6, "label": "해설과 관련도 낮음", "tone": "neutral"},
                {"max": 0.8, "label": "해설과 관련도 보통", "tone": "neutral"},
                {"max": None, "label": "해설과 관련도 높음", "tone": "info"},
            ],
        },
        "화면 판정 구간 (Phase K · Q149) — 키별 [{max, label, tone}] 오름차순, 값이 max 미만인 첫 구간 · 마지막은 max=null. tone = neutral · info · positive · attention · critical",
    ),
    "ui.thresholds": (
        {"planPaceTolerancePp": 5, "headroomAlert": 1, "shareReferencePct": 50, "proposalReasonMin": 5},
        "화면 기준값 (Phase K) — 계획 수준 허용 폭(%p) · 한도 여유 경고 폭 · 구성비 기준선(%) · 제안 사유 최소 글자 수",
    ),
    "ui.goal_roles": (
        {},
        "화면이 집어 쓰는 목표 (Phase K · Q150) — 역할 → 목표 id. 비우면 그 자리는 표시하지 않는다",
    ),
    "ui.scopes": (
        {},
        "업무 영역 (Phase K · Q151) — 종류(hq · dept · branch)별 이름과 단위(조직 + 메뉴 묶음). 화면이 없는 단위는 '준비 중'. 영업점 지점은 BRANCH_SCOPE 규칙",
    ),
    "ui.examples": (
        {"assist": []},
        "예시 질문 (Phase K) — assist = AI 어시스턴트 첫 화면 [{q, hint}] (최대 8개)",
    ),
    "ui.notices": (
        [
            {"countKey": "adminUsers", "label": "가입 승인 대기"},
            {"countKey": "adminUploads", "label": "자료 승인 대기"},
            {"countKey": "adminAnalyses", "label": "분석 에이전트 승인 대기"},
            {"countKey": "adminTodo", "label": "관리자 처리할 일", "fallback": True},
        ],
        "알림 종 목록 (Phase K) — [{countKey, label, fallback}] · 주소는 같은 건수 키를 가진 메뉴 화면. fallback=true 는 다른 알림이 없을 때만",
    ),
    "ui.issue_order": (["breach", "below", "near_limit"], "주요 이슈로 보여 줄 목표 판정과 순서 (Phase K) — breach · below · near_limit · on_track"),
    "ui.labels": (
        {"subDomain": {}, "subDomainHref": {}},
        "화면 표시 이름 · 연결 (Phase K) — subDomain = 하위 영역 코드 → 이름(없는 코드는 코드 그대로), subDomainHref = 하위 영역 → [상세 분석] 화면 주소",
    ),
}
LABEL_GROUPS = {"subDomain": "하위 영역 이름(주목 사항 · 목표의 subDomain)", "subDomainHref": "하위 영역 → 상세 분석 화면 주소"}


class UiConfigError(ValueError):
    pass


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _bands(name: str, v: Any) -> list[dict[str, Any]]:
    if not isinstance(v, list) or not 1 <= len(v) <= 8:
        raise UiConfigError(f"{name}: 구간은 1~8개 목록이어야 합니다")
    out: list[dict[str, Any]] = []
    prev: float | None = None
    for i, b in enumerate(v):
        if not isinstance(b, dict):
            raise UiConfigError(f"{name}: {i + 1}번째 구간 형식 오류")
        label = str(b.get("label") or "").strip()
        if not label or len(label) > 30:
            raise UiConfigError(f"{name}: {i + 1}번째 구간 이름은 1~30자")
        tone = b.get("tone") or "neutral"
        if tone not in TONES:
            raise UiConfigError(f"{name}: 색 {tone} 은 {' · '.join(TONES)} 중 하나")
        mx = b.get("max")
        last = i == len(v) - 1
        if last:
            if mx is not None:
                raise UiConfigError(f"{name}: 마지막 구간의 상한은 비워 두어야 합니다(그 이상 전부)")
        else:
            if not _num(mx):
                raise UiConfigError(f"{name}: {i + 1}번째 구간 상한은 숫자")
            if prev is not None and float(mx) <= prev:
                raise UiConfigError(f"{name}: 상한은 오름차순이어야 합니다")
            prev = float(mx)
        out.append({"max": mx, "label": label, "tone": tone})
    return out


def _org_exists(session: Session, code: Any) -> bool:
    return isinstance(code, str) and session.get(OrgUnit, code) is not None


def validate(session: Session, key: str, value: Any) -> Any:
    """`ui.*` 설정 형식 검사 — 정리한 값을 돌려준다. 모르는 `ui.*` 키(예: ui.as_of)는 그대로."""
    if key == "ui.bands":
        if not isinstance(value, dict):
            raise UiConfigError("구간 설정은 {키: 구간 목록} 형식")
        unknown = set(value) - set(BAND_KEYS)
        if unknown:
            raise UiConfigError(f"알 수 없는 구간 키: {', '.join(sorted(unknown))}")
        return {k: _bands(BAND_KEYS[k].split(" — ")[0], v) for k, v in value.items()}
    if key == "ui.thresholds":
        if not isinstance(value, dict):
            raise UiConfigError("기준값 설정은 {키: 숫자} 형식")
        out = {}
        for k, v in value.items():
            if k not in THRESHOLD_KEYS:
                raise UiConfigError(f"알 수 없는 기준값: {k}")
            label, lo, hi = THRESHOLD_KEYS[k]
            if not _num(v) or not lo <= float(v) <= hi:
                raise UiConfigError(f"{label.split(' — ')[0]}: {lo}~{hi} 사이 숫자")
            out[k] = v
        return out
    if key == "ui.goal_roles":
        if not isinstance(value, dict):
            raise UiConfigError("목표 역할은 {역할: 목표 id} 형식")
        known = goal_ids(session)
        out = {}
        for role, gid in value.items():
            if role not in GOAL_ROLES:
                raise UiConfigError(f"알 수 없는 목표 역할: {role}")
            if gid in (None, ""):
                out[role] = None
                continue
            if not isinstance(gid, str) or (known and gid not in known):
                raise UiConfigError(f"{GOAL_ROLES[role].split('(')[0]}: 목표 {gid} 가 없습니다")
            out[role] = gid
        return out
    if key == "ui.scopes":
        if not isinstance(value, dict) or set(value) - set(SCOPE_KINDS):
            raise UiConfigError("업무 영역은 hq · dept · branch 키")
        out = {}
        sections: set[str] = set()
        for kind, spec in value.items():
            if not isinstance(spec, dict):
                raise UiConfigError(f"{kind}: 형식 오류")
            label = str(spec.get("label") or "").strip()
            if not label or len(label) > 12:
                raise UiConfigError(f"{kind}: 영역 이름은 1~12자")
            units = spec.get("units") or []
            if not isinstance(units, list) or len(units) > 30:
                raise UiConfigError(f"{label}: 단위는 30개까지")
            clean = []
            for u in units:
                if not isinstance(u, dict):
                    raise UiConfigError(f"{label}: 단위 형식 오류")
                org = u.get("org") or None
                section = str(u.get("section") or "").strip()
                if org is not None and not _org_exists(session, org):
                    raise UiConfigError(f"{label}: 조직 {org} 가 없습니다")
                if not section:
                    o = session.get(OrgUnit, org) if org else None
                    section = o.name if o else ""
                if not section or len(section) > 50:
                    raise UiConfigError(f"{label}: 메뉴 묶음 이름이 필요합니다")
                if section in sections:
                    raise UiConfigError(f"메뉴 묶음 {section} 이 두 번 지정됐습니다")
                sections.add(section)
                clean.append({"org": org, "section": section})
            out[kind] = {"label": label, "units": clean}
        return out
    if key == "ui.examples":
        if not isinstance(value, dict):
            raise UiConfigError("예시 질문은 {assist: [...]} 형식")
        out = {}
        for k, items in value.items():
            if k not in ("assist",):
                raise UiConfigError(f"알 수 없는 예시 질문 위치: {k}")
            if not isinstance(items, list) or len(items) > 8:
                raise UiConfigError("예시 질문은 8개까지")
            clean = []
            for it in items:
                q = str((it or {}).get("q") or "").strip() if isinstance(it, dict) else ""
                if not q or len(q) > 120:
                    raise UiConfigError("예시 질문은 1~120자")
                clean.append({"q": q, "hint": str(it.get("hint") or "").strip()[:30]})
            out[k] = clean
        return out
    if key == "ui.notices":
        if not isinstance(value, list) or len(value) > 20:
            raise UiConfigError("알림 목록은 20개까지")
        out_n = []
        for it in value:
            if not isinstance(it, dict) or not COUNT_KEY.match(str(it.get("countKey") or "")):
                raise UiConfigError("알림의 건수 키 형식 오류(영문 · 숫자)")
            label = str(it.get("label") or "").strip()
            if not label or len(label) > 40:
                raise UiConfigError("알림 이름은 1~40자")
            out_n.append({"countKey": it["countKey"], "label": label, "fallback": bool(it.get("fallback"))})
        return out_n
    if key == "ui.labels":
        if not isinstance(value, dict) or set(value) - set(LABEL_GROUPS):
            raise UiConfigError(f"표시 이름 묶음은 {' · '.join(LABEL_GROUPS)}")
        out_l: dict[str, dict[str, str]] = {}
        for group, mapping in value.items():
            if not isinstance(mapping, dict) or len(mapping) > 100:
                raise UiConfigError(f"{group}: {{코드: 이름}} 형식 · 100개까지")
            clean_l = {}
            for code, name in mapping.items():
                text = str(name or "").strip()
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", str(code)) or not text or len(text) > (80 if group.endswith("Href") else 30):
                    raise UiConfigError(f"{group}: 코드(영문 · 숫자) · 값 확인 — {code}")
                if group.endswith("Href") and (not re.fullmatch(r"/[A-Za-z0-9_\-/]{0,79}", text) or ".." in text):
                    raise UiConfigError(f"{group}: 주소는 / 로 시작하는 화면 경로 — {code}")
                clean_l[str(code)] = text
            out_l[group] = clean_l
        return out_l
    if key == "ui.issue_order":
        if not isinstance(value, list) or not all(v in VERDICTS for v in value) or len(set(value)) != len(value):
            raise UiConfigError(f"이슈 판정은 {' · '.join(VERDICTS)} 중 중복 없이")
        return list(value)
    return value


def goal_ids(session: Session) -> set[str]:
    """지정할 수 있는 목표 id — 현재 목표 산출물 + 사용자가 추가한 목표."""
    from nhdip.views.store import get_current

    ids: set[str] = set()
    goals = get_current(session, "goals")
    if isinstance(goals, list):
        ids |= {str(g.get("id")) for g in goals if isinstance(g, dict) and g.get("id")}
    from nhdip.views.user_state import NS_GOAL_ADDED, get_ns

    ids |= set(get_ns(session, NS_GOAL_ADDED))
    return ids


def value_of(session: Session, key: str) -> Any:
    """저장값을 검사해 돌려주고, 없거나 깨졌으면 기본값. 사전형은 기본값 위에 덮는다(새 항목이 생겨도 빠지지 않게)."""
    default = copy.deepcopy(DEFAULTS[key][0])
    s = session.get(Setting, key)
    if s is None or s.value is None:
        return default
    try:
        v = validate(session, key, s.value)
    except UiConfigError:
        return default
    if isinstance(default, dict) and isinstance(v, dict) and key != "ui.scopes":
        return {**default, **v}
    return v


def section_scopes(session: Session, scopes: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """메뉴 묶음 이름 → {scope, orgCode, orgName} (업무 영역 설정의 단위와 매칭)."""
    scopes = scopes if scopes is not None else value_of(session, "ui.scopes")
    out: dict[str, dict[str, Any]] = {}
    for kind, spec in scopes.items():
        for u in spec.get("units") or []:
            org = session.get(OrgUnit, u["org"]) if u.get("org") else None
            out[u["section"]] = {"scope": kind, "orgCode": org.code if org else None, "orgName": org.name if org else u["section"]}
    return out


def hq_org_name(session: Session) -> str | None:
    """종기부(hq) 영역 첫 단위의 조직 이름 — 담당 조직을 정하지 못했을 때의 기본값."""
    for u in value_of(session, "ui.scopes").get("hq", {}).get("units") or []:
        org = session.get(OrgUnit, u["org"]) if u.get("org") else None
        if org is not None:
            return org.name
        if u.get("section"):
            return str(u["section"])
    return None


def _units(session: Session, scopes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """종류별 단위 — 화면이 있는지(활성 화면이 그 메뉴 묶음에 있는지)와 첫 화면 주소."""
    rows = session.execute(select(Screen).where(Screen.active, Screen.kind.in_(["flow", "reference"])).order_by(Screen.sort)).scalars().all()
    home: dict[str, str] = {}
    for r in rows:
        if r.kind == "flow":
            home.setdefault(r.section, r.path)
    for r in rows:
        home.setdefault(r.section, r.path)
    out: dict[str, dict[str, Any]] = {}
    for kind, spec in scopes.items():
        units = []
        for u in spec.get("units") or []:
            org = session.get(OrgUnit, u["org"]) if u.get("org") else None
            units.append({"code": org.code if org else None, "name": org.name if org else u["section"], "section": u["section"], "home": home.get(u["section"]), "available": u["section"] in home})
        out[kind] = {"label": spec["label"], "units": units}
    return out


def office_list(session: Session, user: Any) -> dict[str, Any]:
    """볼 수 있는 계산 대상 지점 — `/screens/branch/offices` 와 같은 값 (B.47 · BRM-05)."""
    from nhdip.orgs import can_view_office, org_of_office
    from nhdip.scopes import office_scope, resolve_office, scoped_key
    from nhdip.views.store import get_current

    from nhdip.orgs import branch_of, office_code_of
    from nhdip.scopes import computed_offices

    from sqlalchemy import select

    from nhdip.models import OrgUnit

    primary, _ = office_scope(session)
    computed = computed_offices(session)
    ready = set(computed)
    br = branch_of(session, user.org_code) if getattr(user, "org_code", None) else None
    mine = office_code_of(session, br.code) if br is not None else None
    # 영업점 직원 — 자기 지점 하나. 관리자 · 영업본부 — 볼 수 있는 모든 영업점(조직표)을 고를 수 있게:
    # 자료로 계산된 지점을 먼저(기본 지점 후보), 나머지는 '자료 대기'로 뒤에. 설정 규칙의 기본 지점이 자료 없이 먼저 보이지 않는다
    if mine:
        cands = [mine]
    else:
        org_offices = [office_code_of(session, c) for c in session.execute(
            select(OrgUnit.code).where(OrgUnit.unit_type == "BRANCH", OrgUnit.active).order_by(OrgUnit.sort, OrgUnit.code)).scalars()]
        cands = [*computed, *org_offices]  # 규칙에만 있고 조직표에 없는 지점 코드는 넣지 않는다
    out = []
    for code in dict.fromkeys(c for c in cands if c):
        if not can_view_office(session, user, code):
            continue
        v = get_current(session, scoped_key("branch_dashboard", code, primary))
        org = org_of_office(session, code)
        name = ((v or {}).get("office") or {}).get("name") if isinstance(v, dict) else None
        out.append({"code": code, "name": name or (org.name if org else code), "available": code in ready, "primary": code == primary})
    return {"offices": out, "default": resolve_office(session, user, None)}


def client_config(session: Session, user: Any, *, branch: bool) -> dict[str, Any]:
    """`/me/menu.config` — 화면이 쓰는 설정 전부. branch=False 면 지점 목록은 비운다(영업점 화면 권한 없음)."""
    scopes = value_of(session, "ui.scopes")
    units = _units(session, scopes)
    owner_orgs = [u["name"] for kind in ("hq", "dept") for u in units.get(kind, {}).get("units", []) if u.get("code")]
    return {
        "bands": value_of(session, "ui.bands"),
        "thresholds": value_of(session, "ui.thresholds"),
        "goalRoles": value_of(session, "ui.goal_roles"),
        "examples": value_of(session, "ui.examples"),
        "notices": value_of(session, "ui.notices"),
        "issueOrder": value_of(session, "ui.issue_order"),
        "labels": value_of(session, "ui.labels"),
        "scopes": units,
        "ownerOrgs": list(dict.fromkeys(owner_orgs)),
        "offices": office_list(session, user) if branch else {"offices": [], "default": None},
    }


def admin_meta(session: Session) -> dict[str, Any]:
    """관리자 [화면 설정] 양식 정보 — 항목 설명 · 선택지(목표 · 조직 · 메뉴 묶음 · 건수 키)."""
    from nhdip.views.store import get_current

    goals = get_current(session, "goals")
    from nhdip.views.user_state import NS_GOAL_ADDED, get_ns

    goal_opts = [{"id": g["id"], "title": g.get("title") or g["id"]} for g in (goals if isinstance(goals, list) else []) if isinstance(g, dict) and g.get("id")]
    goal_opts += [{"id": k, "title": str((v or {}).get("title") or k)} for k, v in get_ns(session, NS_GOAL_ADDED).items() if k not in {g["id"] for g in goal_opts}]
    orgs = session.execute(select(OrgUnit).where(OrgUnit.active).order_by(OrgUnit.sort)).scalars().all()
    screens = session.execute(select(Screen).where(Screen.active).order_by(Screen.sort)).scalars().all()
    sections = list(dict.fromkeys(s.section for s in screens if s.kind in ("flow", "reference")))
    count_keys = list(dict.fromkeys(s.count_key for s in screens if s.count_key))
    return {
        "bandKeys": BAND_KEYS,
        "thresholdKeys": {k: {"label": v[0], "min": v[1], "max": v[2]} for k, v in THRESHOLD_KEYS.items()},
        "goalRoles": GOAL_ROLES,
        "labelGroups": LABEL_GROUPS,
        "tones": list(TONES),
        "verdicts": list(VERDICTS),
        "scopeKinds": list(SCOPE_KINDS),
        "goals": goal_opts,
        "orgs": [{"code": o.code, "name": o.name, "unitType": o.unit_type} for o in orgs],
        "sections": sections,
        "countKeys": count_keys,
        "values": {k: value_of(session, k) for k in DEFAULTS},
        "defaults": {k: v[0] for k, v in DEFAULTS.items()},
        "descriptions": {k: v[1] for k, v in DEFAULTS.items()},
    }
