"""데이터셋 적재 — 파싱 · 품질 검증 · 버전 확정 · 롤백 (ING-01~07).

데이터 형식이 바뀌면 코드가 아니라 `cfg.dataset` 정의(컬럼 · 별칭 · 파서 · 품질 규칙)를 바꾼다.
당행(bank)과 외부(ext)는 정의의 origin 에 따라 다른 스키마에 저장된다.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from nhdip.config import get_settings
from nhdip.events import audit, emit
from nhdip.models import Dataset, source, utcnow


class IngestError(ValueError):
    pass


# ═════════════════════════ 파싱 ═════════════════════════
def _norm(s: Any) -> str:
    return re.sub(r"[\s_\-()·./]+", "", str(s or "")).lower()


def _read_table(content: bytes, filename: str, parser: dict[str, Any]) -> list[dict[str, Any]]:
    name = filename.lower()
    if name.endswith(".json"):
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("rows") or data.get("data") or []
        if not isinstance(data, list):
            raise IngestError("JSON 은 행 목록이어야 합니다")
        return [dict(r) for r in data]
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        ws = wb[parser["sheet"]] if parser.get("sheet") in wb.sheetnames else wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        header_idx = int(parser.get("header_row", 1)) - 1
        header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(rows[header_idx])]
        out = []
        for r in rows[header_idx + 1 :]:
            if r is None or all(v is None or str(v).strip() == "" for v in r):
                continue
            out.append({header[i]: r[i] for i in range(min(len(header), len(r)))})
        return out
    if name.endswith((".csv", ".txt", ".tsv")):
        text = content.decode(parser.get("encoding", "utf-8-sig"), errors="replace")
        delim = "\t" if name.endswith(".tsv") else parser.get("delimiter", ",")
        skip = int(parser.get("skip_rows", 0))
        lines = text.splitlines()[skip:]
        return [dict(r) for r in csv.DictReader(lines, delimiter=delim)]
    raise IngestError("지원 형식: .csv · .tsv · .xlsx · .json")


def _coerce(value: Any, typ: str) -> Any:
    if value is None or (isinstance(value, str) and value.strip() in ("", "-")):
        return None
    if typ in ("int", "integer"):
        return int(Decimal(str(value).replace(",", "")))
    if typ in ("num", "number", "decimal", "float"):
        try:
            return float(Decimal(str(value).replace(",", "")))
        except InvalidOperation as exc:
            raise ValueError(f"숫자 아님: {value!r}") from exc
    if typ == "bool":
        return str(value).strip().lower() in ("1", "y", "yes", "true", "t", "예")
    if typ == "date":
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        s = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y%m%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"날짜 아님: {value!r}")
    s = str(value).strip()
    if isinstance(value, float) and value.is_integer():
        s = str(int(value))
    return s


def map_rows(ds: Dataset, raw_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """원본 헤더 → 정의 컬럼 매핑 + 형 변환. (행, 오류 목록)"""
    if not raw_rows:
        return [], ["행이 없습니다"]
    headers = list(raw_rows[0].keys())
    hmap: dict[str, str] = {}
    errors: list[str] = []
    for col in ds.columns:
        cands = [col["name"], col.get("label", ""), *col.get("aliases", [])]
        found = next((h for h in headers if _norm(h) in {_norm(c) for c in cands if c}), None)
        if found is not None:
            hmap[col["name"]] = found
        elif col.get("required"):
            errors.append(f"필수 컬럼 없음: {col['name']} (허용 헤더: {', '.join(c for c in cands if c)})")
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_rows, start=1):
        row: dict[str, Any] = {}
        for col in ds.columns:
            h = hmap.get(col["name"])
            try:
                row[col["name"]] = _coerce(raw.get(h) if h else None, col.get("type", "str"))
            except ValueError as exc:
                errors.append(f"{i}행 {col['name']}: {exc}")
                row[col["name"]] = None
        rows.append(row)
    return rows, errors


# ═════════════════════════ 품질 검증 ═════════════════════════
def _ym_index(v: Any) -> int | None:
    """'202608' · '2026-08' · '2026-08-31' → 월 일련번호."""
    t = re.sub(r"[^0-9]", "", str(v or ""))
    if len(t) < 6:
        return None
    y, m = int(t[:4]), int(t[4:6])
    return y * 12 + (m - 1) if 1 <= m <= 12 else None


def quality_check(ds: Dataset, rows: list[dict[str, Any]], parse_errors: list[str], previous: list[dict[str, Any]] | None = None, privacy: dict[str, Any] | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(rule: str, passed: bool, detail: str, severity: str = "error"):
        checks.append({"rule": rule, "passed": passed, "detail": detail, "severity": severity})

    add("parse", not parse_errors, "; ".join(parse_errors[:10]) or "헤더·형 변환 정상")
    for col in ds.columns:
        if col.get("required"):
            missing = sum(1 for r in rows if r.get(col["name"]) is None)
            add(f"not_null:{col['name']}", missing == 0, f"결측 {missing}건")
    if ds.key_columns:
        keys = [tuple(r.get(k) for k in ds.key_columns) for r in rows]
        dup = len(keys) - len(set(keys))
        add("unique_key", dup == 0, f"키({', '.join(ds.key_columns)}) 중복 {dup}건")
    for rule in ds.quality_rules or []:
        kind = rule.get("rule")
        sev = rule.get("severity", "error")
        col = rule.get("column")
        if kind == "range":
            lo, hi = rule.get("min"), rule.get("max")
            bad = [r[col] for r in rows if r.get(col) is not None and ((lo is not None and r[col] < lo) or (hi is not None and r[col] > hi))]
            add(f"range:{col}", not bad, f"범위({lo}~{hi}) 밖 {len(bad)}건", sev)
        elif kind == "allowed":
            allowed = set(rule.get("values", []))
            bad = {r.get(col) for r in rows if r.get(col) not in allowed}
            add(f"allowed:{col}", not bad, f"허용 외 값 {sorted(map(str, bad))[:5]}", sev)
        elif kind == "le_column":
            other = rule.get("other")
            bad = sum(1 for r in rows if r.get(col) is not None and r.get(other) is not None and r[col] > r[other])
            add(f"le:{col}<={other}", bad == 0, f"{col} > {other} 인 행 {bad}건", sev)
        elif kind == "sum_equals":
            # 상세 행 합계 = 합계 행 값 (허용 오차 %) — 그룹 컬럼별
            flag, val, group, tol = rule["total_flag"], rule["column"], rule.get("group"), float(rule.get("tolerance_pct", 0.1))
            groups = {r.get(group) for r in rows} if group else {None}
            worst = 0.0
            for g in groups:
                part = [r for r in rows if not group or r.get(group) == g]
                total = sum(r[val] or 0 for r in part if r.get(flag))
                detail = sum(r[val] or 0 for r in part if not r.get(flag))
                if total:
                    worst = max(worst, abs(detail - total) / abs(total) * 100)
            add(f"sum_equals:{val}", worst <= tol, f"상세 합계 오차 최대 {worst:.3f}% (허용 {tol}%)", sev)
        elif kind == "period_continuity":
            # 기간 연속성 — 그룹별로 처음~마지막 월 사이 빠진 월 (1.4)
            group = rule.get("group")
            gaps: list[str] = []
            for g in sorted({r.get(group) for r in rows} if group else {None}, key=str):
                idx = sorted({i for r in rows if (not group or r.get(group) == g) for i in [_ym_index(r.get(col))] if i is not None})
                missing = [i for i in range(idx[0], idx[-1] + 1) if i not in set(idx)] if idx else []
                if missing:
                    gaps.append(f"{g or '전체'}: " + ", ".join(f"{i // 12}{i % 12 + 1:02d}" for i in missing[:6]))
            add(f"continuity:{col}", not gaps, "; ".join(gaps[:5]) or "빠진 기간 없음", sev)
        elif kind == "max_change":
            # 급변 경고 — 직전 현재 버전 대비 같은 키 값의 변화율이 기준(%)을 넘는 행 (1.4)
            if previous is None:
                continue
            keys, pct = rule.get("keys") or ds.key_columns, float(rule.get("pct", 50))
            before = {tuple(r.get(k) for k in keys): r.get(col) for r in previous}
            spikes = []
            for r in rows:
                b, a = before.get(tuple(r.get(k) for k in keys)), r.get(col)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b != 0 and abs(a - b) / abs(b) * 100 > pct:
                    spikes.append(f"{'/'.join(str(r.get(k)) for k in keys)} {b:,.0f}→{a:,.0f}")
            add(f"max_change:{col}", not spikes, f"직전 버전 대비 {pct:g}% 넘게 바뀐 행 {len(spikes)}건" + (f" — {'; '.join(spikes[:3])}" if spikes else ""), sev)
        elif kind == "min_rows":
            add("min_rows", len(rows) >= int(rule.get("value", 1)), f"{len(rows)}행 (최소 {rule.get('value')})", sev)
    # 개인정보 형식 값 검사 (B.32) — 주민등록번호 · 휴대전화 · 이메일 · 카드번호가 섞이면 적재 거부 (설정 privacy.policy)
    from nhdip.privacy import DEFAULTS as PRIVACY_DEFAULTS, LABELS as PII_LABELS, scan_rows

    pol = {**PRIVACY_DEFAULTS, **(privacy or {})}
    if pol.get("pii_scan", True):
        allow = set(pol.get("pii_allow_columns") or []) | {c["name"] for c in ds.columns if c.get("pii_ok")}
        res = scan_rows(rows, allow)
        found = ", ".join(f"{PII_LABELS[k]} {n}건" for k, n in res["found"].items())
        where = "; ".join(f"{x['row']}행 {x['column']}({x['kind']})" for x in res["samples"][:5])
        add("pii", not res["found"], f"개인정보 형식 값 {found} — {where} (허용 열은 설정 privacy.policy.pii_allow_columns)" if res["found"] else "개인정보 형식 값 없음")
    failed = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    warned = [c for c in checks if not c["passed"] and c["severity"] != "error"]
    status = "failed" if failed else ("warning" if warned else "passed")
    return {"status": status, "checks": checks, "rows": len(rows)}


# ═════════════════════════ 버전 확정 ═════════════════════════
def _store_file(origin: str, code: str, filename: str, content: bytes) -> tuple[str, str]:
    sha = hashlib.sha256(content).hexdigest()
    base = os.path.join(get_settings().filestore_dir, origin, code)
    try:
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, f"{sha[:16]}_{os.path.basename(filename)}")
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(content)
    except OSError:
        path = ""  # 파일 볼륨이 없으면(테스트 등) 체크섬만 남긴다
    return sha, path


def to_date(v: Any) -> str | None:
    """기준일 컬럼 값(YYYYMM · YYYY-MM-DD · YYYY.MM) → ISO 날짜 문자열(월 단위면 말일)."""
    import calendar

    if v is None:
        return None
    s = str(v).strip().replace(".", "").replace("/", "")
    if len(s) == 6 and s.isdigit():
        y, m = int(s[:4]), int(s[4:])
        if 1 <= m <= 12:
            return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
    s2 = str(v).strip()
    if len(s2) == 10 and s2[4] == "-":
        return s2
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return None


def _row_key(ds: Dataset, row: dict[str, Any]) -> str | None:
    if not ds.key_columns:
        return None
    return "|".join(str(row.get(k)) for k in ds.key_columns)[:300]


def ingest_rows(
    session: Session,
    ds: Dataset,
    rows: list[dict[str, Any]],
    *,
    quality: dict[str, Any],
    file_name: str | None,
    file_sha: str | None = None,
    file_path: str | None = None,
    as_of: str | None = None,
    data_origin: str = "simulated",
    actor: str | None = None,
    note: str | None = None,
    force: bool = False,
):
    """버전 생성 → (품질 통과 시) 확정 + 현재 버전 교체 + 아웃박스 이벤트 — 한 트랜잭션."""
    from nhdip.locks import lock

    t = source(ds.origin)
    lock(session, f"ds:{ds.origin}:{ds.code}")  # 동시 업로드 · 되돌리기 직렬화 — 버전 번호 · 현재 버전 교체가 겹치지 않도록 (B.32)
    last = session.execute(
        select(t.version.version).where(t.version.dataset_code == ds.code).order_by(t.version.version.desc()).limit(1)
    ).scalar()
    commit = quality["status"] != "failed" or force
    if not as_of and ds.as_of_column:
        vals = {r.get(ds.as_of_column) for r in rows if r.get(ds.as_of_column) is not None}
        if len(vals) == 1:
            as_of = to_date(next(iter(vals)))
    v = t.version(
        dataset_code=ds.code,
        version=(last or 0) + 1,
        as_of=date.fromisoformat(as_of) if as_of else None,
        data_origin=data_origin,
        status="committed" if commit else "rejected",
        is_current=False,
        file_name=file_name,
        file_sha256=file_sha,
        file_path=file_path,
        row_count=len(rows),
        quality=quality,
        note=note,
        uploaded_by=actor,
        committed_at=utcnow() if commit else None,
    )
    session.add(v)
    session.flush()
    for i, r in enumerate(rows, start=1):
        row_as_of = to_date(r.get(ds.as_of_column)) if ds.as_of_column else None
        session.add(
            t.row(
                version_id=v.id,
                dataset_code=ds.code,
                row_no=i,
                row_key=_row_key(ds, r),
                as_of=date.fromisoformat(row_as_of) if row_as_of else None,
                data=r,
            )
        )
    if commit:
        # 같은 기준일 구획(partition)의 이전 현재 버전만 교체 — 다른 기준일 데이터는 유지
        same = t.version.as_of == v.as_of if v.as_of else t.version.as_of.is_(None)
        session.execute(update(t.version).where(t.version.dataset_code == ds.code, t.version.id != v.id, same).values(is_current=False))
        v.is_current = True
        emit(
            session,
            "dataset.committed",
            {"dataset": ds.code, "origin": ds.origin, "kind": ds.kind, "version": v.version, "version_id": v.id, "rows": len(rows)},
            actor,
        )
    audit(session, actor, "dataset.upload", "dataset", ds.code, {"version": v.version, "status": v.status, "quality": quality["status"], "file": file_name})
    return v


def _read_any(content: bytes, filename: str, ds: Dataset) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """원본 보고서 양식(2633 · 2020 · 7790)이면 어댑터로, 아니면 일반 표 파서로 읽는다 (1.3.2)."""
    if filename.lower().endswith(".xlsx"):
        from .adapters import AdapterError, parse_report

        try:
            parsed = parse_report(content, filename, ds.code, ds.parser or {})
        except AdapterError as exc:
            raise IngestError(str(exc)) from exc
        if parsed is not None:
            if not parsed.rows:
                raise IngestError(f"{parsed.adapter}: 읽은 값이 없습니다")
            return parsed.rows, {"adapter": parsed.adapter, "meta": parsed.meta, "notes": parsed.notes}
    return _read_table(content, filename, ds.parser or {}), None


def ingest_file(session: Session, ds: Dataset, filename: str, content: bytes, **kw):
    raw, source = _read_any(content, filename, ds)
    rows, errors = map_rows(ds, raw)
    from nhdip.privacy import policy as privacy_policy

    _, prev = current_rows(session, ds)
    quality = quality_check(ds, rows, errors, previous=prev, privacy=privacy_policy(session))
    if source:
        quality["source"] = source  # 원본 양식 · 머리글 메타(조회일자 · 조회사무소 · 기준일 · 단위) · 변환 메모
    sha, path = _store_file(ds.origin, ds.code, filename, content)
    return ingest_rows(session, ds, rows, quality=quality, file_name=filename, file_sha=sha, file_path=path, **kw)


def preview_file(ds: Dataset, filename: str, content: bytes) -> dict[str, Any]:
    raw, source = _read_any(content, filename, ds)
    rows, errors = map_rows(ds, raw)
    return {"headers": list(raw[0].keys()) if raw else [], "rows": rows[:20], "quality": quality_check(ds, rows, errors), "source": source}


def rollback(session: Session, ds: Dataset, version_id: int, actor: str | None):
    """같은 기준일 구획 안에서 지정 버전을 현재 버전으로 되돌린다(이후 버전은 rolled_back 표시)."""
    from nhdip.locks import lock

    t = source(ds.origin)
    lock(session, f"ds:{ds.origin}:{ds.code}")
    target = session.get(t.version, version_id)
    if not target or target.dataset_code != ds.code or target.status not in ("committed", "rolled_back"):
        raise IngestError("되돌릴 수 있는 버전이 아닙니다")
    same = t.version.as_of == target.as_of if target.as_of else t.version.as_of.is_(None)
    for cur in session.execute(select(t.version).where(t.version.dataset_code == ds.code, t.version.is_current, same)).scalars():
        cur.is_current = False
        if cur.version > target.version:
            cur.status = "rolled_back"
    target.is_current = True
    target.status = "committed"
    target.committed_at = utcnow()
    emit(session, "dataset.committed", {"dataset": ds.code, "origin": ds.origin, "kind": ds.kind, "version": target.version, "version_id": target.id, "rollback": True}, actor)
    audit(session, actor, "dataset.rollback", "dataset", ds.code, {"to_version": target.version, "as_of": str(target.as_of) if target.as_of else None})
    return target


def current_versions(session: Session, ds: Dataset) -> list[Any]:
    t = source(ds.origin)
    return list(
        session.execute(
            select(t.version).where(t.version.dataset_code == ds.code, t.version.is_current).order_by(t.version.committed_at.desc(), t.version.id.desc())
        ).scalars()
    )


class VersionSet:
    """여러 기준일 구획의 현재 버전 묶음 — 계보 기록·표시용."""

    def __init__(self, versions: list[Any]):
        self.versions = versions
        latest = versions[0]
        self.id = latest.id
        self.version = latest.version if len(versions) == 1 else "+".join(str(v.version) for v in sorted(versions, key=lambda x: x.version))
        self.file_name = latest.file_name if len(versions) == 1 else f"{len(versions)}개 파일"
        self.data_origin = "actual" if all(v.data_origin == "actual" for v in versions) else "simulated"
        self.as_of = max((v.as_of for v in versions if v.as_of), default=None)
        self.committed_at = latest.committed_at


def current_rows(session: Session, ds: Dataset) -> tuple[VersionSet | None, list[dict[str, Any]]]:
    """모든 기준일 구획의 현재 버전 행. 같은 기준일 값이 여러 버전에 있으면 최근 확정 버전을 쓴다."""
    t = source(ds.origin)
    versions = current_versions(session, ds)
    if not versions:
        return None, []
    claimed: set[str] = set()
    out: list[dict[str, Any]] = []
    for v in versions:
        rows = session.execute(select(t.row.data).where(t.row.version_id == v.id).order_by(t.row.row_no)).scalars().all()
        if ds.as_of_column:
            mine = {str(r.get(ds.as_of_column)) for r in rows}
            rows = [r for r in rows if str(r.get(ds.as_of_column)) not in claimed]
            claimed |= mine
        # 행 단위 계보(어느 버전·파일에서 왔는지) — 계산 근거 표시에 사용
        out.extend({**r, "__v": v.version, "__file": v.file_name} for r in rows)
    return VersionSet(versions), out
