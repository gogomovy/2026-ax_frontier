"""컬럼 정의서 → mart 테이블 적재 + 화면값 대조 (요구사항 DCT-01~08, 설계 §19.10).

1) 계약(cfg.column_contract)의 TYPE 으로 mart.<접두>_<표코드> 테이블을 만들고, 새 컬럼은 ALTER 로 추가한다.
2) 컬럼별 바인딩으로 값을 채운다 — 수치는 같은 실행에서 커널이 계산한 지표, 서술은 Critic 을 통과한 문장.
3) 정의서의 '화면값/목업값' 과 지표 표시값을 단위 환산 후 비교한다(일치 · 불일치 · 기대값 없음 · 미연결).
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from nhdip.calc import round_display
from nhdip.calc.metrics import EvalContext
from nhdip.models import ColumnContract, Setting
from nhdip.views.store import find_insight

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
TYPE_RE = re.compile(r"^(CHAR|VARCHAR|DECIMAL|NUMERIC|INTEGER|INT|BIGINT|TEXT|DATE|JSON|JSONB)(?:\((\d+)(?:,(\d+))?\))?$")
# 숫자 뒤에 단위가 오거나, 단위 없이 끝나는 경우만 값으로 본다 ('3개년' · '5C' 같은 표현은 제외)
NUM = re.compile(r"([+-]?\d[\d,]*(?:\.\d+)?)(?:\s*(%p|%|조원|억원|백만원|건)|(?![\d.,가-힣A-Za-z]))")
UNIT_MN = {"조원": Decimal(1_000_000), "억원": Decimal(100), "백만원": Decimal(1)}
METRIC_MN = {"KRW_TN": Decimal(1_000_000), "KRW_BN": Decimal(100), "KRW_MN": Decimal(1)}


def _setting(session: Session, key: str, default: Any) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None else default


def mart_table(session: Session, table_code: str, dept: str) -> str:
    prefix = _setting(session, "contracts.dept_prefix", {"종기부": "hq"}).get(dept, "t")
    code = table_code.lower()
    if code.startswith(f"{prefix}_"):
        code = code[len(prefix) + 1 :]  # RISK_T01 → risk_t01 (접두 중복 없이)
    name = f"{prefix}_{code}"
    if not IDENT.match(name):
        raise ValueError(f"mart 테이블 이름 오류: {name}")
    return name


def sql_type(c: ColumnContract) -> str:
    t = (c.data_type or "").replace(" ", "").upper()
    m = TYPE_RE.match(t)
    if not m:
        return "TEXT" if c.column_name.endswith("_TEXT") else "NUMERIC(24,6)"
    base, p, s = m.groups()
    if base in ("CHAR", "VARCHAR"):
        return f"{base}({int(p or 255)})"
    if base in ("DECIMAL", "NUMERIC"):
        return f"NUMERIC({int(p or 24)},{int(s or 0)})"
    return {"INT": "INTEGER", "JSON": "JSONB"}.get(base, base)


def scale_of(c: ColumnContract) -> int | None:
    m = TYPE_RE.match((c.data_type or "").replace(" ", "").upper())
    if m and m.group(1) in ("DECIMAL", "NUMERIC"):
        return int(m.group(3) or 0)
    return None


def ensure_table(session: Session, table: str, cols: list[ColumnContract]) -> list[str]:
    """테이블 생성 · 새 컬럼 추가. 기본키 = 정의서 PK ∪ BASE_YM(이력 보존)."""
    notes: list[str] = []
    names = [c.column_name.lower() for c in cols]
    for n in names:
        if not IDENT.match(n):
            raise ValueError(f"컬럼 이름 오류: {n}")
    pk = [c.column_name.lower() for c in cols if c.is_pk]
    if "base_ym" in names and "base_ym" not in pk:
        pk.insert(0, "base_ym")
        notes.append("기본키에 BASE_YM 추가(월별 이력 보존)")
    exists = session.execute(text("SELECT 1 FROM information_schema.tables WHERE table_schema='mart' AND table_name=:t"), {"t": table}).first()
    if exists:
        cur_pk = [
            r[0]
            for r in session.execute(
                text(
                    "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = ('mart.' || quote_ident(:t))::regclass AND i.indisprimary ORDER BY array_position(i.indkey, a.attnum)"
                ),
                {"t": table},
            )
        ]
        if sorted(cur_pk) != sorted(pk):
            # 정의서의 기본키가 바뀌면 기존 테이블을 보관하고 새로 만든다(이력 데이터는 보관본에 남는다)
            from datetime import datetime

            archive = f"{table}__{datetime.now():%Y%m%d%H%M%S}"
            session.execute(text(f'ALTER TABLE mart."{table}" RENAME TO "{archive}"'))
            notes.append(f"기본키 변경({', '.join(cur_pk)} → {', '.join(pk)}) — 기존 테이블 mart.{archive} 로 보관")
            exists = None
    if not exists:
        defs = [f'"{c.column_name.lower()}" {sql_type(c)}' + (" NOT NULL" if c.column_name.lower() in pk else "") for c in cols]
        defs += ['"_run_id" VARCHAR(32)', '"_generated_at" TIMESTAMPTZ DEFAULT now()']
        if pk:
            defs.append(f"PRIMARY KEY ({', '.join(chr(34) + p + chr(34) for p in pk)})")
        session.execute(text(f'CREATE TABLE mart."{table}" ({", ".join(defs)})'))
        notes.append(f"mart.{table} 생성")
    else:
        have = {r[0] for r in session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='mart' AND table_name=:t"), {"t": table})}
        for c in cols:
            if c.column_name.lower() not in have:
                session.execute(text(f'ALTER TABLE mart."{table}" ADD COLUMN "{c.column_name.lower()}" {sql_type(c)}'))
                notes.append(f"컬럼 추가 {c.column_name}")
    return notes


def parse_expected(s: str | None) -> tuple[Decimal | None, str | None, int]:
    """'21,865억원' → (21865, '억원', 0) · '+0.8%p' → (0.8, '%p', 1). 숫자가 없으면 (None, None, 0)."""
    if not s:
        return None, None, 0
    m = NUM.search(s)
    if not m:
        return None, None, 0
    raw = m.group(1).replace(",", "")
    dec = len(raw.split(".")[1]) if "." in raw else 0
    return Decimal(raw), m.group(2), dec


def compare(expected_text: str | None, display: Decimal | None, metric_unit: str) -> tuple[str, str]:
    exp, unit, dec = parse_expected(expected_text)
    if exp is None:
        return "no_expected", "정의서에 비교할 숫자 없음"
    if display is None:
        return "mismatch", "계산값 없음"
    got = Decimal(display)
    if unit in UNIT_MN and metric_unit in METRIC_MN:
        exp = exp * UNIT_MN[unit] / METRIC_MN[metric_unit]
    tol = Decimal(1).scaleb(-dec) / 2 + Decimal("1e-9")
    if unit in UNIT_MN and metric_unit in METRIC_MN:
        tol = tol * UNIT_MN[unit] / METRIC_MN[metric_unit]
    diff = got - exp
    if abs(diff) <= tol:
        return "match", ""
    return "mismatch", f"계산 {got} vs 정의서 {exp.normalize():f} (차이 {diff.normalize():f})"


UNIT_TEXT = {"PCT": "%", "PP": "%p", "KRW_TN": "조원", "KRW_BN": "억원", "KRW_MN": "백만원", "CNT": "건", "RATIO": ""}
FIG_RE = re.compile(r"\[\[fig:([^\]]+)\]\]")
TERM_RE = re.compile(r"\{\{term:[^|}]+\|([^}]+)\}\}")


def render_markers(s: str | None, figures: dict[str, Any]) -> str | None:
    """서술의 [[fig:ID]] 를 확정 수치 표시로, {{term:..|라벨}} 을 라벨로 — mart 에는 읽을 수 있는 문장으로 저장."""
    if not s:
        return s

    def fig(m: re.Match) -> str:
        f = figures.get(m.group(1))
        if not isinstance(f, dict) or f.get("value") is None:
            return f.get("undefinedLabel", "-") if isinstance(f, dict) else "-"
        d = f.get("decimals") or 0
        v = Decimal(str(f["value"]))
        sign = "+" if f.get("unit") == "PP" and v > 0 else ""
        unit = UNIT_TEXT.get(f.get("unit"), "")
        if unit and m.string.startswith(unit, m.end()):
            unit = ""  # 서술이 마커 뒤에 단위를 또 쓴 경우(예: '12건건') 한 번만 (B.40)
        return f"{sign}{v:,.{d}f}{unit}"

    return TERM_RE.sub(lambda m: m.group(1), FIG_RE.sub(fig, s))


def _latest_ym(ctx: EvalContext, dataset: str) -> str | None:
    _, rows, _ = ctx.dataset(dataset)
    vals = sorted({str(r.get("ym")) for r in rows if r.get("ym")})
    return vals[-1] if vals else None


def _plain(text: str | None) -> str | None:
    if not text:
        return text
    return TERM_RE.sub(lambda m: m.group(1), text)


def resolve_binding(ctx: EvalContext, c: ColumnContract, artifacts: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, Any]:
    b = c.binding or {}
    run = run or {}
    if "row" in b:
        return {"kind": "row", "col": b["row"]}
    if "dataset" in b:
        # 원천 정의(S 시트) — 데이터셋 정의에 그 컬럼이 있는지 검사(값은 데이터셋에 있음)
        from nhdip.models import Dataset

        ds = ctx.session.get(Dataset, b["dataset"])
        cols = {x["name"] for x in (ds.columns if ds else [])}
        ok = ds is not None and (not b.get("column") or b["column"] in cols)
        return {"kind": "source", "ok": ok, "ref": f"{b['dataset']}.{b.get('column') or '*'}", "reason": None if ok else ("데이터셋 없음" if ds is None else f"데이터셋에 {b.get('column')} 없음")}
    if "analysis" in b:
        return {"kind": "derived", "value": run.get("analysis_id") if b["analysis"] == "id" else run.get("analysis_dt")}
    if "evidence" in b:
        ins = find_insight(artifacts, b["evidence"]) or {}
        refs = []
        for e in ins.get("evidence") or []:
            d = e.get("doc") or {}
            if d or e.get("docId"):
                refs.append({"doc": e.get("docId") or d.get("fileName") or d.get("title"), "title": d.get("title"), "page": d.get("page"), "category": e.get("category")})
        import json as _json

        return {"kind": "text", "value": _json.dumps(refs, ensure_ascii=False) if refs else None, "ref": b["evidence"]}
    if "report" in b:
        rep = artifacts.get(b["report"])
        if not isinstance(rep, dict):
            return {"kind": "text", "value": None, "ref": b["report"]}
        if b.get("field") == "title":
            return {"kind": "text", "value": rep.get("title"), "ref": f"{b['report']}.title"}
        if b.get("section"):
            sec = next((x for x in rep.get("sections") or [] if x.get("id") == b["section"]), None) or {}
            parts: list[str] = []
            for blk in sec.get("blocks") or []:
                if blk.get("text"):
                    parts.append(blk["text"])
                for it in blk.get("items") or []:
                    parts.append(it if isinstance(it, str) else str(it.get("text") or ""))
                for kv in blk.get("kv") or []:
                    if isinstance(kv, dict) and kv.get("value"):
                        parts.append(f"{kv.get('label', '')}: {kv['value']}.")
            return {"kind": "text", "value": render_markers(" ".join(p for p in parts if p).strip() or None, rep.get("figures") or {}), "ref": f"{b['report']}#{b['section']}"}
        from nhdip.reports import export

        try:
            data, _, _ = export(ctx.session, rep, "html")
            return {"kind": "text", "value": data.decode("utf-8", "ignore"), "ref": b["report"]}
        except Exception as exc:  # noqa: BLE001
            return {"kind": "text", "value": None, "ref": b["report"], "error": f"보고서 변환 실패: {exc}"}
    if "plan" in b:
        pl = next((x for x in artifacts.get("action_plans") or [] if x.get("id") == b["plan"]), None) or {}
        return {"kind": "text", "value": _plain(pl.get(b.get("field", "body"))), "ref": b["plan"]}
    if "metric" in b:
        oc = ctx.outcomes.get(b["metric"])
        if oc is None:
            return {"kind": "metric", "error": f"이 실행에서 계산되지 않은 지표: {b['metric']}"}
        if oc.error:
            return {"kind": "metric", "error": oc.error}
        raw = oc.value
        if b.get("field") and b["field"] != "value":
            raw = oc.extra.get(b["field"])
        sc = scale_of(c)
        stored = round_display(Decimal(str(raw)), sc) if raw is not None and sc is not None else raw
        disp = oc.display if not b.get("field") else round_display(Decimal(str(raw)), oc.decimals, scale=None)
        return {"kind": "metric", "value": stored, "display": disp, "unit": oc.unit, "calc_run_id": oc.calc_run_id, "formula": oc.formula}
    if "base_ym" in b:
        return {"kind": "base_ym", "value": _latest_ym(ctx, b["base_ym"])}
    if "const" in b:
        return {"kind": "const", "value": b["const"]}
    if "version" in b:
        return {"kind": "version"}
    if "insight" in b:
        ins = find_insight(artifacts, b["insight"]) or {}
        return {"kind": "text", "value": render_markers(ins.get(b.get("field", "statement")), ins.get("figures") or {}), "ref": b["insight"]}
    if "proposal" in b:
        p = next((x for x in artifacts.get("proposals") or [] if x.get("id") == b["proposal"]), None) or {}
        figs = p.get("figures") or {}
        if isinstance(figs, list):
            figs = {f.get("id"): f for f in figs if isinstance(f, dict)}
        return {"kind": "text", "value": render_markers(p.get(b.get("field", "judgement")), figs), "ref": b["proposal"]}
    return {"kind": "unmapped", "reason": b.get("unmapped") or "바인딩 미지정", "question": b.get("question")}


def materialize(session: Session, ctx: EvalContext, artifacts: dict[str, Any], tables: list[str] | None, run_id: str | None) -> dict[str, Any]:
    contracts = session.execute(select(ColumnContract).where(ColumnContract.active).order_by(ColumnContract.table_code, ColumnContract.seq)).scalars().all()
    by_table: dict[str, list[ColumnContract]] = {}
    for c in contracts:
        if not tables or c.table_code in tables:
            by_table.setdefault(c.table_code, []).append(c)
    reports: dict[str, Any] = {}
    builders = _setting(session, "contracts.row_builders", {}) or {}
    for code, cols in by_table.items():
        if code in builders or any("row" in (c.binding or {}) or "dataset" in (c.binding or {}) for c in cols):
            reports[code] = _materialize_rows(session, ctx, artifacts, code, cols, builders.get(code), run_id)
            continue
        table = mart_table(session, code, cols[0].dept)
        notes = ensure_table(session, table, cols)
        row: dict[str, Any] = {}
        checks: list[dict[str, Any]] = []
        version_col = None
        for c in cols:
            r = resolve_binding(ctx, c, artifacts)
            col = c.column_name.lower()
            verdict, note = "unmapped", r.get("reason") or r.get("error") or ""
            if r["kind"] == "version":
                version_col = col
                verdict, note = "derived", "제안 버전"
            elif r.get("error"):
                verdict = "error"
            elif r["kind"] == "metric":
                row[col] = r["value"]
                # 결정으로 정정한 기대값(binding.expected)이 있으면 그 값으로 대조하고 정의서 원값은 메모로 남긴다
                exp = (c.binding or {}).get("expected") or c.expected_text
                verdict, note = compare(exp, r["display"], r["unit"])
                if (c.binding or {}).get("expected"):
                    note = f"{note} · 정정 기대값 {exp} (정의서 {c.expected_text}) — {(c.binding or {}).get('expected_note', '')}".strip(" ·")
            elif r["kind"] in ("base_ym", "const"):
                row[col] = r["value"]
                verdict, note = "derived", ""
            elif r["kind"] == "text":
                row[col] = r["value"]
                verdict, note = ("text", "") if r["value"] else ("error", f"서술 없음: {r.get('ref')}")
            checks.append(
                {
                    "column": c.column_name,
                    "kor": c.kor_name,
                    "kind": r["kind"],
                    "binding": c.binding,
                    "value": None if r.get("value") is None else (str(r["value"]) if not isinstance(r.get("value"), str) else r["value"][:300]),
                    "display": None if r.get("display") is None else str(r["display"]),
                    "unit": r.get("unit"),
                    "expected": c.expected_text,
                    "isMock": c.is_mock,
                    "source": c.source_desc,
                    "sourceColumn": c.source_column,
                    "verdict": verdict,
                    "note": note,
                    "question": r.get("question"),
                    "calcRunId": r.get("calc_run_id"),
                }
            )
        if version_col:
            row[version_col] = _next_version(session, table, version_col, row)
        _upsert(session, table, cols, row, run_id)
        summary: dict[str, int] = {}
        for ch in checks:
            summary[ch["verdict"]] = summary.get(ch["verdict"], 0) + 1
        reports[code] = {"table": f"mart.{table}", "name": cols[0].table_name, "dept": cols[0].dept, "baseYm": row.get("base_ym"), "summary": summary, "columns": checks, "notes": notes}
    return reports


def _numeric_cols(row: dict[str, Any], version_col: str) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k != version_col and not (isinstance(v, str) and len(v) > 40)}


def _next_version(session: Session, table: str, version_col: str, row: dict[str, Any]) -> int:
    """같은 기준년월의 최근 제안과 수치가 같으면 버전 유지, 다르면 +1."""
    base = row.get("base_ym")
    last = session.execute(text(f'SELECT * FROM mart."{table}" WHERE base_ym = :b ORDER BY "{version_col}" DESC LIMIT 1'), {"b": base}).mappings().first() if base else None
    if not last:
        return 1
    cur = _numeric_cols(row, version_col)
    same = all(_eq(last.get(k), v) for k, v in cur.items())
    return int(last[version_col]) if same else int(last[version_col]) + 1


def _eq(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:  # noqa: BLE001
        return str(a) == str(b)


def _upsert(session: Session, table: str, cols: list[ColumnContract], row: dict[str, Any], run_id: str | None) -> None:
    names = [c.column_name.lower() for c in cols if c.column_name.lower() in row]
    pk = [c.column_name.lower() for c in cols if c.is_pk and c.column_name.lower() in row]
    if "base_ym" in row and "base_ym" not in pk:
        pk.insert(0, "base_ym")
    if pk:
        where = " AND ".join(f'"{k}" = :{k}' for k in pk)
        session.execute(text(f'DELETE FROM mart."{table}" WHERE {where}'), {k: row[k] for k in pk})
    params = {k: (v.quantize(Decimal(1).scaleb(-12), rounding=ROUND_HALF_UP) if isinstance(v, Decimal) else v) for k, v in row.items()}
    jsonb = {c.column_name.lower() for c in cols if sql_type(c) == "JSONB"}
    cols_sql = ", ".join(f'"{n}"' for n in names) + ', "_run_id"'
    vals_sql = ", ".join(f"CAST(:{n} AS JSONB)" if n in jsonb else f":{n}" for n in names) + ", :_run_id"
    session.execute(text(f'INSERT INTO mart."{table}" ({cols_sql}) VALUES ({vals_sql})'), {**params, "_run_id": run_id})


def import_workbook(session: Session, tables: list[dict[str, Any]], workbook: str, default_bindings: dict[str, dict[str, Any]], actor: str | None) -> dict[str, Any]:
    """정의서 반영 — 기존 바인딩 유지, 새 컬럼은 기본 바인딩(없으면 미연결), 빠진 컬럼은 비활성."""
    added = updated = deactivated = 0
    for t in tables:
        seen = set()
        for col in t["columns"]:
            if not col["valid_name"]:
                continue
            seen.add(col["column_name"])
            c = session.execute(select(ColumnContract).where(ColumnContract.table_code == t["table_code"], ColumnContract.column_name == col["column_name"])).scalar()
            fields = {k: col[k] for k in ("seq", "kor_name", "is_pk", "data_type", "source_desc", "source_column", "is_mock", "expected_text")}
            if c is None:
                binding = default_bindings.get(f"{t['table_code']}.{col['column_name']}") or default_bindings.get(col["column_name"]) or {"unmapped": "바인딩 미지정 — 관리자 화면에서 지정"}
                session.add(ColumnContract(table_code=t["table_code"], table_name=t["name"], dept=t["dept"], column_name=col["column_name"], binding=binding, active=True, workbook=workbook, **fields))
                added += 1
            else:
                for k, v in fields.items():
                    setattr(c, k, v)
                c.table_name, c.dept, c.active, c.workbook = t["name"], t["dept"], True, workbook
                updated += 1
        for c in session.execute(select(ColumnContract).where(ColumnContract.table_code == t["table_code"], ColumnContract.active)).scalars():
            if c.column_name not in seen:
                c.active = False
                deactivated += 1
    return {"added": added, "updated": updated, "deactivated": deactivated, "tables": [t["table_code"] for t in tables]}


def _materialize_rows(session: Session, ctx: EvalContext, artifacts: dict[str, Any], code: str, cols: list[ColumnContract], spec: dict[str, Any] | None, run_id: str | None) -> dict[str, Any]:
    """다행 정의서 테이블 (B.38) — 행 생성기(설정 contracts.row_builders)가 만든 행 + 공통 바인딩(지표 · 서술 · 보고서 · 기준월)."""
    from datetime import date

    from nhdip.contracts.rows import ROW_BUILDERS

    run = {"analysis_id": run_id, "analysis_dt": date.today()}
    # 원천 정의(S01~S03) — 행 생성기 없이 데이터셋 바인딩만 있으면 적재하지 않고 원천 컬럼 존재만 검사
    source_only = not spec and any("dataset" in (c.binding or {}) for c in cols) and not any("row" in (c.binding or {}) for c in cols)
    rows: list[dict[str, Any]] = []
    scoped: dict[str, dict[str, Any]] = {}  # 공통 값을 일부 행에만(binding.rows_where — 예: 집계유형 ALL 행)
    err = None
    if spec and not source_only:
        fn = ROW_BUILDERS.get(spec.get("builder", ""))
        if fn is None:
            err = f"행 생성기 없음: {spec.get('builder')}"
        else:
            try:
                rows = fn(ctx, spec.get("params") or {})
            except Exception as exc:  # noqa: BLE001
                err = f"행 생성 실패: {type(exc).__name__}: {exc}"
    common: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []
    version_col: str | None = None
    data_cols: set[str] = set()  # 제안 버전 비교 대상 — 수치 · 코드 열(서술 · 분석 ID · 분석 일자는 실행마다 달라 제외)
    for c in cols:
        r = resolve_binding(ctx, c, artifacts, run)
        col = c.column_name.lower()
        kind = r["kind"]
        if kind in ("row", "metric", "base_ym", "const"):
            data_cols.add(col)
        verdict, note, val, disp = "unmapped", r.get("reason") or r.get("error") or "", None, None
        if kind == "version":
            version_col = col
            verdict, note = "derived", "제안 버전 — 같은 기준월 · 지점의 이전 적재와 수치가 같으면 유지, 다르면 +1"
        elif kind == "source":
            verdict, note = ("mapped" if r["ok"] else "error"), (r["ref"] if r["ok"] else r["reason"])
        elif kind == "row":
            key = r["col"]
            have = [x.get(key) for x in rows if x.get(key) is not None]
            if have:
                verdict, note, val = "row", f"{len(have)}/{len(rows)}행", have[0]
                # 정의서 목업값 대조 — binding.check 로 고른 행(예: grade_cd=6B), 없으면 첫 행
                chk = (c.binding or {}).get("check") or {}
                tgt = next((x for x in rows if all(str(x.get(k)) == str(v) for k, v in chk.items())), rows[0]) if chk else None
                if chk and tgt is not None and c.expected_text:
                    unit = (c.binding or {}).get("unit", "")
                    verdict, note = compare(c.expected_text, tgt.get(key), unit)
                    note = f"{note} · 대조 행 {chk}".strip(" ·")
                    val = tgt.get(key)
            elif (c.binding or {}).get("optional") and rows:
                verdict, note = "empty", f"0/{len(rows)}행 — 원천에 값 없음(선택 항목)"
            else:
                verdict, note = ("unmapped", "원천 없음 — 정의서 '추가 필요'") if c.is_mock else ("error", "행 생성기가 이 값을 만들지 못함")
        elif r.get("error"):
            verdict = "error"
        elif kind == "metric":
            common[col] = r["value"]
            val, disp = r["value"], r["display"]
            exp = (c.binding or {}).get("expected") or c.expected_text
            verdict, note = compare(exp, r["display"], r["unit"])
        elif kind in ("base_ym", "const", "derived"):
            common[col] = r["value"]
            verdict, val = "derived", r["value"]
        elif kind == "text":
            common[col] = r["value"]
            val = r["value"]
            verdict, note = ("text", "") if r["value"] else ("error", f"서술 없음: {r.get('ref')}")
        if col in common and (c.binding or {}).get("rows_where"):
            scoped[col] = (c.binding or {})["rows_where"]
            note = f"{note} · 적용 행 {scoped[col]}".strip(" ·")
        checks.append({"column": c.column_name, "kor": c.kor_name, "kind": kind, "binding": c.binding,
                       "value": None if val is None else (val[:300] if isinstance(val, str) else str(val)), "display": None if disp is None else str(disp),
                       "unit": r.get("unit"), "expected": c.expected_text, "isMock": c.is_mock, "source": c.source_desc, "sourceColumn": c.source_column, "verdict": verdict, "note": note})
    summary: dict[str, int] = {}
    for ch in checks:
        summary[ch["verdict"]] = summary.get(ch["verdict"], 0) + 1
    if err:
        summary["error"] = summary.get("error", 0) + 1
    rep = {"name": cols[0].table_name, "dept": cols[0].dept, "summary": summary, "columns": checks, "notes": [err] if err else [], "rows": len(rows), "kind": "source" if source_only else "rows"}
    if source_only:
        rep["table"] = None
        return rep
    table = mart_table(session, code, cols[0].dept)
    rep["table"] = f"mart.{table}"
    rep["notes"] = rep["notes"] + ensure_table(session, table, cols)
    names = {c.column_name.lower() for c in cols}
    def _common_for(x: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in common.items() if k not in scoped or all(str(x.get(a)) == str(b) for a, b in scoped[k].items())}

    full = [{k: v for k, v in {**_common_for(x), **x}.items() if k in names} for x in rows]
    rep["baseYm"] = full[0].get("base_ym") if full else common.get("base_ym")
    scope: dict[str, Any] = {}
    where = ""
    old: list[dict[str, Any]] = []
    if full and full[0].get("base_ym"):
        # 같은 기준월 · 같은 범위(사무소 등)의 이전 적재는 지우고 다시 넣는다 — 빠진 행이 남지 않도록
        scope = {k: full[0][k] for k in ("base_ym", "brc") if k in full[0]}
        where = " AND ".join(f'"{k}" = :{k}' for k in scope)
        if version_col:
            old = [dict(m) for m in session.execute(text(f'SELECT * FROM mart."{table}" WHERE {where}'), scope).mappings()]
        session.execute(text(f'DELETE FROM mart."{table}" WHERE {where}'), scope)
    for x in full:
        _upsert(session, table, cols, x, run_id)
    if version_col and scope:
        # 다행 표의 제안 버전(B.46 · Q96) — 저장된 값(열 정밀도로 반올림된 값)끼리 비교하려고 다시 읽어서 판단한다
        new = [dict(m) for m in session.execute(text(f'SELECT * FROM mart."{table}" WHERE {where}'), scope).mappings()]
        ver = rows_version(old, new, sorted(data_cols - {version_col}), version_col)
        session.execute(text(f'UPDATE mart."{table}" SET "{version_col}" = :_ver WHERE {where}'), {**scope, "_ver": ver})
        rep["version"] = ver
        for ch in checks:
            if ch["column"].lower() == version_col:
                ch["value"] = str(ver)
    return rep


def _norm_cell(v: Any) -> Any:
    if v is None or isinstance(v, bool):
        return v
    try:
        return str(Decimal(str(v)).normalize())
    except Exception:  # noqa: BLE001
        return str(v)


def rows_version(old: list[dict[str, Any]], new: list[dict[str, Any]], cols: list[str], version_col: str) -> int:
    """다행 표 제안 버전 — 이전 적재가 없거나 버전이 비어 있으면 1, 행 집합(비교 열 기준)이 같으면 이전 버전 유지, 다르면 +1.
    행 순서와 무관하게 비교한다. 서술 · 분석 ID · 분석 일자 같은 실행마다 바뀌는 열은 cols 에 넣지 않는다."""
    prev = max((int(r[version_col]) for r in old if r.get(version_col) is not None), default=None)
    if prev is None:
        return 1
    import json as _json

    def sig(rows: list[dict[str, Any]]) -> list[str]:
        return sorted(_json.dumps([_norm_cell(r.get(c)) for c in cols], ensure_ascii=False, default=str) for r in rows)

    return prev if sig(old) == sig(new) else prev + 1
