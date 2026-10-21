"""조직정보 · 인사정보 .dat 동기화 (Phase R · 가이드 §3).

관리자가 [사용자 · 권한 › 조직 · 인사 동기화]에서 .dat 를 올린다. 순서: 조직 → 인사. 구분자 '|'(빈 끝 칸 유지), 인코딩 UTF-8(BOM) → EUC-KR(CP949).

조직 .dat (0부터, 최소 15칸)  0 법인 · 1 사무소코드(키) · 2 사무소명 · 3/4 모점1 · 5/6 모점2 · 7/8 본부 · 9 조직코드 · 10 순번 · 11 트리 레벨 · 12/13 시도 · 26 사용여부(Y)
인사 .dat (0부터, 최소 21칸)  0 개인번호(키 · SSO 사번) · 1 성명 · 2 법인 · 3 직원구분 · 4 재직 · 5/6 직급 · 7/8 직명 · 11/12 시도 · 13/14 사무소 · 15~20 모점1~3

이 플랫폼에 맞춘 방식
- 조직 → iam.org_unit (code = 사무소코드, source='dat'). 상위 = 모점1(자기 자신이면 모점2 → 본부). 유형은 이름 끝말 규칙(설정 sync.org_type_rules)
- 인사 → iam.app_user (emp_no = 개인번호, source='dat', 비밀번호 없음 = SSO 전용). 역할 · 데이터 책임자 · 관리자 지정은 바꾸지 않는다
- 가이드 구현의 알려진 문제를 고친다: 한 트랜잭션(실패하면 전부 되돌림) · 필터 규칙 해석 실패면 중단 · CSV 값 trim ·
  조직은 지우지 않고 파일에서 빠진 dat 조직만 사용 안 함(30% 안전장치) · 미리보기(dry-run)
- 수동 조직(업무 구성 · 관리자 생성)은 같은 코드가 와도 이름 · 사용 여부만 맞추고 상위 · 유형은 그대로(설정 sync.overwrite_manual_orgs)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import AppUser, OrgUnit, Setting, UserSession, utcnow

ORG_MIN_FIELDS = 15
EMP_MIN_FIELDS = 21
DEACTIVATE_LIMIT_PCT = 30
MAX_ERRORS = 200
ALPHA = re.compile(r"[A-Za-z]")
EMP_RE = re.compile(r"^[0-9A-Za-z]{1,20}$")
ORG_RE = re.compile(r"^[0-9A-Za-z_\-]{1,32}$")
DEFAULT_TYPE_RULES = [
    {"pattern": "(지점|출장소|금융센터|지소|영업소)$", "type": "BRANCH"},
    {"pattern": "(지역본부|영업본부)$", "type": "REGION"},
    {"pattern": "본부$", "type": "HQ_DIV"},
    {"pattern": "[부단]$", "type": "DEPT"},
    {"pattern": "국$", "type": "BUREAU"},
    {"pattern": "팀$", "type": "TEAM"},
]
FILTER_KEYS = {"corpType", "regionCode", "regionCodes", "parent3Code", "parent3Codes", "parent2Code", "parent2Codes"}


class SyncError(ValueError):
    """동기화를 시작할 수 없는 오류(필터 규칙 · 파일) — 아무것도 바꾸지 않는다."""


@dataclass
class SyncResult:
    kind: str
    dry_run: bool
    total_processed: int = 0
    matched: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    reactivated: int = 0
    skipped: int = 0
    encoding: str = "utf-8"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        if len(self.warnings) < 50:
            self.warnings.append(msg)

    def err(self, msg: str) -> None:
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(msg)
        elif len(self.errors) == MAX_ERRORS:
            self.errors.append("… 오류가 더 있습니다(앞 200건만)")

    def json(self) -> dict[str, Any]:
        return {"kind": self.kind, "dryRun": self.dry_run, "totalProcessed": self.total_processed, "matched": self.matched, "inserted": self.inserted, "updated": self.updated,
                "unchanged": self.unchanged, "deactivated": self.deactivated, "reactivated": self.reactivated, "skipped": self.skipped, "encoding": self.encoding,
                "errors": self.errors, "warnings": self.warnings}


# ═════════════════════════ 읽기 ═════════════════════════
def decode(content: bytes) -> tuple[str, str, list[str]]:
    """(본문, 인코딩, 안내) — 호스트 연계 파일이 어떤 모양으로 와도 읽는다.

    사내 인사 · 조직 .dat 는 내려주는 시스템에 따라 모양이 섞여 온다. 아래를 모두 받아 같은 텍스트로 만든다.
      · UTF-8 (BOM 있거나 없거나) · EUC-KR(CP949) — 두 파일이 서로 다른 인코딩으로 와도 각각 알아서 읽는다
      · UTF-16 (LE · BE, BOM 없어도 NUL 패턴으로 알아낸다)
      · 고정길이 레코드의 NUL(0x00) 패딩 — 제거한다(값에 남으면 코드 · 사번 비교가 조용히 틀린다)
      · 줄바꿈 CRLF · CR · LF 섞임
    바꾼 내용은 안내로 돌려주어 동기화 결과의 '참고'에 남긴다(조용히 고치지 않는다).
    """
    notes: list[str] = []
    raw = content

    # ── UTF-16 — BOM 또는 NUL 이 절반 가까이면(ASCII 본문의 UTF-16 특징) ──
    utf16 = None
    if raw[:2] == b"\xff\xfe":
        utf16 = "utf-16-le"
    elif raw[:2] == b"\xfe\xff":
        utf16 = "utf-16-be"
    else:
        head = raw[:4096]
        if head and head.count(0) * 100 // max(len(head), 1) >= 25:
            for cand in ("utf-16-le", "utf-16-be"):
                try:
                    probe = raw[: 4096 * 2].decode(cand)
                except UnicodeDecodeError:
                    continue
                if "|" in probe:
                    utf16 = cand
                    break
    if utf16:
        text = raw.decode(utf16, errors="replace").lstrip("\ufeff")
        notes.append(f"{utf16.upper()} 로 저장된 파일을 읽었습니다 — 가능하면 UTF-8 로 내려 주세요")
        return text, utf16, notes

    # ── NUL 패딩 제거 (고정길이 레코드) ──
    nul = raw.count(0)
    if nul:
        raw = raw.replace(b"\x00", b"")
        notes.append(f"빈 자리 채움 문자(NUL) {nul:,}개를 지우고 읽었습니다")

    # ── UTF-8 → EUC-KR(CP949) ──
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "utf-8-sig", notes
    try:
        return raw.decode("utf-8"), "utf-8", notes
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
        if "\ufffd" in text:
            notes.append("읽을 수 없는 글자가 있어 일부를 물음표로 바꿨습니다 — 인코딩을 확인해 주세요")
        return text, "euc-kr", notes


# 줄바꿈 · 탭만 남기고 제어문자를 지운다. splitlines() 는 \x0b · \x0c · \x85 에서도 줄을 쪼개므로 split("\n") 을 쓴다
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def lines(content: bytes) -> tuple[list[tuple[int, list[str]]], str, list[str]]:
    text, enc, notes = decode(content)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for i, ln in enumerate(text.split("\n"), start=1):
        if not ln.strip():
            continue
        # 빈 끝 칸 유지(split 기본) · 칸마다 제어문자 제거 후 공백 정리
        out.append((i, [_CTRL.sub("", c).strip() for c in ln.split("|")]))
    return out, enc, notes


def _v(p: list[str], i: int) -> str | None:
    return (p[i] or None) if i < len(p) else None


# ═════════════════════════ 필터 규칙 ═════════════════════════
def filter_rules(session: Session) -> list[dict[str, set[str]]]:
    """설정 sync.filter_rules — 규칙끼리 OR, 규칙 안 키끼리 AND. 형식이 틀리면 동기화를 멈춘다(가이드 문제 7 · 8)."""
    s = session.get(Setting, "sync.filter_rules")
    raw = s.value if s is not None else []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError as exc:
            raise SyncError(f"필터 규칙(sync.filter_rules) JSON 오류 — {exc}") from exc
    if not isinstance(raw, list):
        raise SyncError("필터 규칙(sync.filter_rules)은 목록이어야 합니다 — 예: [{\"corpType\":\"1\",\"regionCode\":\"01\"}]")
    rules = []
    for i, r in enumerate(raw, start=1):
        if not isinstance(r, dict) or not r:
            raise SyncError(f"필터 규칙 {i}번이 객체가 아닙니다")
        bad = set(r) - FILTER_KEYS
        if bad:
            raise SyncError(f"필터 규칙 {i}번에 모르는 키: {', '.join(sorted(bad))} (쓸 수 있는 키: {', '.join(sorted(FILTER_KEYS))})")
        norm: dict[str, set[str]] = {}
        for k, v in r.items():
            vals = {x.strip() for x in str(v).split(",") if x.strip()}
            if not vals:
                raise SyncError(f"필터 규칙 {i}번 {k} 값이 비었습니다")
            base = k[:-1] if k.endswith("Codes") else k
            norm.setdefault(base, set()).update(vals)
        rules.append(norm)
    return rules


def _emp_match(rules: list[dict[str, set[str]]], p: list[str]) -> bool:
    if not rules:
        return True
    field_of = {"corpType": 2, "regionCode": 11, "parent3Code": 19, "parent2Code": 17}
    return any(all((_v(p, field_of[k]) or "") in vals for k, vals in r.items()) for r in rules)


def _org_match(rules: list[dict[str, set[str]]], p: list[str]) -> bool:
    if not rules:
        return True

    def ok(k: str, vals: set[str]) -> bool:
        if k == "corpType":
            return (_v(p, 0) or "") in vals
        if k == "regionCode":
            return (_v(p, 12) or "") in vals
        if k == "parent3Code":  # 본부 코드 또는 본부 자신
            return (_v(p, 7) or "") in vals or (_v(p, 1) or "") in vals
        if k == "parent2Code":
            return (_v(p, 5) or "") in vals or (_v(p, 1) or "") in vals
        return False

    return any(all(ok(k, vals) for k, vals in r.items()) for r in rules)


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None and s.value is not None else default


def type_rules(session: Session) -> list[tuple[re.Pattern[str], str]]:
    out = []
    for r in _setting(session, "sync.org_type_rules", DEFAULT_TYPE_RULES) or []:
        try:
            out.append((re.compile(str(r["pattern"])), str(r["type"])))
        except (KeyError, TypeError, re.error):
            continue
    return out


def unit_type_of(name: str, rules: list[tuple[re.Pattern[str], str]]) -> str | None:
    return next((t for rx, t in rules if rx.search(name or "")), None)


# ═════════════════════════ 조직 ═════════════════════════
def sync_organizations(session: Session, content: bytes, *, dry_run: bool = False) -> SyncResult:
    from nhdip.orgs import recompute_levels

    res = SyncResult("organization", dry_run)
    rules = filter_rules(session)
    rows, res.encoding, notes = lines(content)
    for n in notes:
        res.warn(n)
    if not rows:
        raise SyncError("빈 파일입니다")
    parsed: dict[str, list[str]] = {}
    for ln, p in rows:
        res.total_processed += 1
        if len(p) < ORG_MIN_FIELDS:
            res.err(f"{ln}행: 필드 수 부족({len(p)} < {ORG_MIN_FIELDS})")
            continue
        code, name = _v(p, 1), _v(p, 2)
        if not code or not name:
            res.err(f"{ln}행: 사무소코드 · 사무소명이 비었습니다")
            continue
        if not ORG_RE.match(code):
            res.err(f"{ln}행: 사무소코드 형식 오류({code[:20]})")
            continue
        if code in parsed:
            res.warnings.append(f"{ln}행: 사무소코드 {code} 중복 — 뒤 행으로")
        parsed[code] = p
    # 필터 — 직접 맞는 조직 + 그 하위 조직(모점1 · 모점2 가 맞는 조직)을 더 늘지 않을 때까지 (가이드 3-5 2차)
    if rules:
        matched = {c for c, p in parsed.items() if _org_match(rules, p)}
        grew = True
        while grew:
            grew = False
            for c, p in parsed.items():
                if c not in matched and ((_v(p, 3) or "") in matched or (_v(p, 5) or "") in matched):
                    matched.add(c)
                    grew = True
    else:
        matched = set(parsed)
    res.matched = len(matched)
    res.skipped = len(parsed) - len(matched)
    trules = type_rules(session)
    overwrite_manual = bool(_setting(session, "sync.overwrite_manual_orgs", False))
    sp = session.begin_nested() if dry_run else None
    try:
        existing = {o.code: o for o in session.execute(select(OrgUnit)).scalars()}
        parent_of: dict[str, str | None] = {}
        before: dict[str, tuple[Any, ...]] = {}
        for code in sorted(matched):
            p = parsed[code]
            p1, p2, hq = _v(p, 3), _v(p, 5), _v(p, 7)
            parent = p1 if p1 and p1 != code else (p2 if p2 and p2 != code else (hq if hq and hq != code else None))
            if len(p) > 26:
                active = (p[26] or "").upper() == "Y"
            else:
                # 가이드 원본은 칸이 없으면 '사용 안 함'으로 넣지만, 짧은 파일 하나로 조직이 모두 꺼지지 않게 '사용'으로 둔다
                res.warn(f"사무소 {code}: 사용여부(27번째 칸)가 없어 '사용'으로 둡니다")
                active = True
            ext = {"corpType": _v(p, 0), "parent1": p1, "parent1Name": _v(p, 4), "parent2": p2, "parent2Name": _v(p, 6), "hqCode": hq, "hqName": _v(p, 8), "deptCode": _v(p, 9),
                   "sortOrder": _v(p, 10), "treeLevel": _v(p, 11), "regionCode": _v(p, 12), "regionName": _v(p, 13), "syncedAt": utcnow().isoformat()}
            try:
                sort = int(_v(p, 10) or 0)
            except ValueError:
                sort = 0
            name = _v(p, 2) or code
            o = existing.get(code)
            if o is None:
                o = OrgUnit(code=code, name=name[:100], level=1, unit_type=unit_type_of(name, trules), parent_code=None, active=active, sort=sort, source="dat", ext=ext)
                session.add(o)
                existing[code] = o
                res.inserted += 1
                parent_of[code] = parent
                continue
            manual = (o.source or "manual") != "dat"
            before[code] = (o.name, o.active, o.parent_code, o.unit_type, o.sort)
            o.name, o.active = name[:100], active
            o.ext = {**(o.ext or {}), **ext}
            if not manual or overwrite_manual:
                o.sort = sort
                o.unit_type = unit_type_of(name, trules) or o.unit_type
                parent_of[code] = parent
        session.flush()
        # 상위 조직 — 모두 만든 뒤에 잇는다(파일 순서와 무관). 없는 상위 · 순환은 끊고 알린다
        for code, parent in parent_of.items():
            if parent and parent not in existing:
                res.warn(f"사무소 {code}: 상위 {parent} 가 없어 최상위로 둡니다")
                parent = None
            seen, cur = {code}, parent
            while cur:
                if cur in seen:
                    res.warn(f"사무소 {code}: 상위 관계 순환({parent}) — 최상위로 둡니다")
                    parent = None
                    break
                seen.add(cur)
                nxt = existing.get(cur)
                cur = parent_of.get(cur, nxt.parent_code if nxt is not None else None)
            existing[code].parent_code = parent
            parent_of[code] = parent
        session.flush()
        for code, b in before.items():
            o = existing[code]
            changed = b != (o.name, o.active, o.parent_code, o.unit_type, o.sort)
            res.updated += int(changed)
            res.unchanged += int(not changed)
        # 파일에서 빠진 dat 조직 — 지우지 않고 사용 안 함(필터 범위 밖 조직은 건드리지 않음 · 30% 안전장치)
        if not rules:
            gone = [o for o in existing.values() if o.source == "dat" and o.active and o.code not in parsed]
            live = [o for o in existing.values() if o.source == "dat" and o.active]
            if gone and live and len(gone) * 100 / len(live) > DEACTIVATE_LIMIT_PCT:
                res.warnings.append(f"파일에 없는 동기화 조직 {len(gone)}곳(활성의 {len(gone) * 100 // len(live)}%) — {DEACTIVATE_LIMIT_PCT}% 를 넘어 파일 이상으로 보고 사용 안 함 처리를 건너뜁니다")
            else:
                for o in gone:
                    o.active = False
                    res.deactivated += 1
        recompute_levels(session)
        session.flush()
    except Exception:
        if sp is not None:
            sp.rollback()
        raise
    if sp is not None:
        sp.rollback()
    return res


# ═════════════════════════ 인사 ═════════════════════════
def _revoke(session: Session, emp: str) -> None:
    for us in session.execute(select(UserSession).where(UserSession.emp_no == emp, UserSession.revoked_at.is_(None))).scalars():
        us.revoked_at = utcnow()


def sync_employees(session: Session, content: bytes, *, dry_run: bool = False) -> SyncResult:
    res = SyncResult("employee", dry_run)
    rules = filter_rules(session)
    rows, res.encoding, notes = lines(content)
    for n in notes:
        res.warn(n)
    if not rows:
        raise SyncError("빈 파일입니다")
    sp = session.begin_nested() if dry_run else None
    try:
        orgs = {o.code: o for o in session.execute(select(OrgUnit)).scalars()}
        users = {u.emp_no: u for u in session.execute(select(AppUser)).scalars()}
        all_ids: set[str] = set()
        for ln, p in rows:
            res.total_processed += 1
            if len(p) < EMP_MIN_FIELDS:
                res.err(f"{ln}행: 필드 수 부족({len(p)} < {EMP_MIN_FIELDS})")
                continue
            emp, name = _v(p, 0), _v(p, 1)
            if not emp or not name:
                res.err(f"{ln}행: 개인번호 · 성명이 비었습니다")
                continue
            if not EMP_RE.match(emp):
                res.err(f"{ln}행: 개인번호 형식 오류({emp[:20]})")
                continue
            all_ids.add(emp)  # 필터 전에 — 비활성화 판단 기준(가이드 3-6)
            if not _emp_match(rules, p):
                res.skipped += 1
                continue
            res.matched += 1
            office = _v(p, 13)
            org = next((orgs[c] for c in (office, _v(p, 15), _v(p, 17), _v(p, 19)) if c and c in orgs), None)
            if org is None:
                res.err(f"{ln}행: {emp} 소속 사무소 {office or '-'} 가 조직에 없습니다 — 조직 .dat 를 먼저 올리세요")
                continue
            if org.code != office:
                res.warn(f"{emp}: 사무소 {office} 가 없어 상위 {org.code} 로 둡니다")
            hr = {"corpType": _v(p, 2), "employeeType": _v(p, 3), "employmentStatus": _v(p, 4), "positionCode": _v(p, 5), "position": _v(p, 6), "titleCode": _v(p, 7), "title": _v(p, 8),
                  "regionCode": _v(p, 11), "regionName": _v(p, 12), "officeCode": office, "officeName": _v(p, 14), "parent1Code": _v(p, 15), "parent1Name": _v(p, 16),
                  "parent2Code": _v(p, 17), "parent2Name": _v(p, 18), "parent3Code": _v(p, 19), "parent3Name": _v(p, 20), "syncedAt": utcnow().isoformat()}
            position = (_v(p, 8) or _v(p, 6) or "")[:30] or None
            u = users.get(emp)
            if u is None:
                u = AppUser(emp_no=emp, name=name[:50], password_hash="", org_code=org.code, position=position, role="user", status="active", source="dat", hr=hr)
                session.add(u)
                users[emp] = u
                res.inserted += 1
                continue
            before = (u.name, u.org_code, u.position, u.status)
            # 동기화 필드만 — 역할 · 데이터 책임자 · 데이터 관리자 · 비밀번호는 그대로
            u.name, u.org_code, u.position = name[:50], org.code, position
            u.hr = {**{k: v for k, v in (u.hr or {}).items() if k != "deactivatedBySync"}, **hr}
            if u.source == "local" and not u.password_hash:
                u.source = "dat"
            if u.status == "disabled" and (u.hr or {}).get("deactivatedAt") and (u.source == "dat"):
                u.status = "active"  # 동기화로 중지했던 사람이 다시 파일에 — 다시 켠다
                u.hr = {k: v for k, v in u.hr.items() if k != "deactivatedAt"}
                res.reactivated += 1
            changed = before != (u.name, u.org_code, u.position, u.status)
            res.updated += int(changed)
            res.unchanged += int(not changed)
        session.flush()
        # 비활성화 — 파일 전체(필터 전)에 없는 dat 사용자. 관리자 · 영문 포함(외부 직원) 사번 제외 · 30% 안전장치 (가이드 3-6)
        if all_ids:
            live = [u for u in users.values() if u.source == "dat" and u.status == "active"]
            gone = [u for u in live if u.emp_no not in all_ids and not ALPHA.search(u.emp_no) and u.role != "admin"]
            if gone and live and len(gone) * 100 / len(live) > DEACTIVATE_LIMIT_PCT:
                res.warnings.append(f"파일에 없는 동기화 사용자 {len(gone)}명(활성의 {len(gone) * 100 // len(live)}%) — {DEACTIVATE_LIMIT_PCT}% 를 넘어 파일 이상으로 보고 사용 중지를 건너뜁니다")
            else:
                now = utcnow().isoformat()
                for u in gone:
                    u.status = "disabled"
                    u.hr = {**(u.hr or {}), "deactivatedAt": now}
                    _revoke(session, u.emp_no)
                    res.deactivated += 1
        session.flush()
    except Exception:
        if sp is not None:
            sp.rollback()
        raise
    if sp is not None:
        sp.rollback()
    return res
