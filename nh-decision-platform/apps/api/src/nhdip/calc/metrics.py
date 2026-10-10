"""지표 평가 엔진 — `cfg.metric` 정의(입력 참조 + 커널 수식)를 계산해 calc_run · metric_value 로 남긴다.

입력 참조 형식 (관리자 화면에서 편집)
  {"q": {"dataset": 코드, "where": {...}, "col": 컬럼, "agg": sum|first|list|count|max|min, "order_by": 컬럼}}
       where 값: 스칼라(=) · {"in": [...]} · {"in_dataset": {"dataset": 코드, "col": 컬럼, "where": {...}}}
  {"metric": 지표코드, "field": "value"|추가필드}    다른 지표 결과 (같은 실행 또는 최근 값)
  {"rule": 규칙코드, "path": "a.b"}                  활성 규칙 버전 본문 값
  {"setting": 키}                                     cfg.setting 값
  {"const": 값}                                       상수 (가능하면 rule/setting 사용)
각 참조에 "label" · "unit" 을 두면 화면의 계산 근거(calc trace)에 그대로 표시된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.data.datasets import current_rows
from nhdip.models import Dataset, Metric, MetricValue, Rule, RuleVersion, Setting

from . import formulas
from .kernel import run_and_record


@dataclass
class MetricOutcome:
    code: str
    label: str
    formula: str
    value: Decimal | None
    display: Decimal | None
    extra: dict[str, Any]
    calc_run_id: str
    error: str | None
    trace: dict[str, Any]
    figure_ids: list[str]
    unit: str
    decimals: int | None
    data_origin: str = "simulated"
    previous: Decimal | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "formula": self.formula,
            "value": None if self.value is None else str(self.value),
            "display": None if self.display is None else float(self.display),
            "previous": None if self.previous is None else float(self.previous),
            "extra": formulas_jsonable(self.extra),
            "calc_run_id": self.calc_run_id,
            "error": self.error,
        }


def formulas_jsonable(v: Any) -> Any:
    from .kernel import _jsonable

    return _jsonable(v)


class ResolveError(ValueError):
    pass


@dataclass
class EvalContext:
    session: Session
    workflow_run_id: str | None = None
    rows: dict[str, tuple[Any, list[dict[str, Any]], Dataset]] = field(default_factory=dict)
    outcomes: dict[str, MetricOutcome] = field(default_factory=dict)
    used_versions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def dataset(self, code: str):
        if code not in self.rows:
            ds = self.session.get(Dataset, code)
            if not ds:
                raise ResolveError(f"데이터셋 없음: {code}")
            v, rows = current_rows(self.session, ds)
            if not v:
                raise ResolveError(f"확정된 버전 없음: {code}")
            self.rows[code] = (v, rows, ds)
            self.used_versions[code] = {"dataset": code, "origin": ds.origin, "version": v.version, "version_id": v.id, "file": v.file_name, "data_origin": v.data_origin}
        return self.rows[code]


def _match(row: dict[str, Any], where: dict[str, Any], ctx: EvalContext) -> bool:
    for k, cond in (where or {}).items():
        val = row.get(k)
        if isinstance(cond, dict):
            if "in" in cond:
                if val not in cond["in"]:
                    return False
            elif "in_dataset" in cond:
                spec = cond["in_dataset"]
                _, rows, _ = ctx.dataset(spec["dataset"])
                allowed = {r.get(spec["col"]) for r in rows if _match(r, spec.get("where") or {}, ctx)}
                if val not in allowed:
                    return False
            elif "ne" in cond:
                if val == cond["ne"]:
                    return False
            elif "not" in cond:
                if bool(val) == bool(cond["not"]):
                    return False
        elif str(val) != str(cond) if not isinstance(cond, bool) else bool(val) != cond:
            return False
    return True


TOKEN_RE = __import__("re").compile(r"^\$(latest|earliest)(?:-(\d+))?$")


def _shift(value: str, months: int) -> str:
    """YYYYMM · YYYY-MM-DD 값을 months 만큼 이전으로."""
    s = str(value)
    if len(s) == 6 and s.isdigit():
        y, m = int(s[:4]), int(s[4:])
        t = y * 12 + (m - 1) - months
        return f"{t // 12:04d}{t % 12 + 1:02d}"
    if len(s) == 10 and s[4] == "-":
        import calendar

        y, m = int(s[:4]), int(s[5:7])
        t = y * 12 + (m - 1) - months
        yy, mm = t // 12, t % 12 + 1
        return f"{yy:04d}-{mm:02d}-{calendar.monthrange(yy, mm)[1]:02d}"
    raise ResolveError(f"기간 이동을 지원하지 않는 값: {value}")


def resolve_token(rows: list[dict[str, Any]], col: str, token: Any) -> Any:
    """'$latest' · '$earliest' · '$latest-12'(12개월 전) 을 실제 값으로."""
    if not isinstance(token, str):
        return token
    m = TOKEN_RE.match(token)
    if not m:
        return token
    vals = sorted({str(r.get(col)) for r in rows if r.get(col) is not None})
    if not vals:
        raise ResolveError(f"{col}: 값 없음")
    base = vals[-1] if m.group(1) == "latest" else vals[0]
    return _shift(base, int(m.group(2))) if m.group(2) else base


def resolve_where(ctx: "EvalContext", rows: list[dict[str, Any]], where: dict[str, Any] | None) -> dict[str, Any]:
    """조건의 토큰·참조를 확정 값으로 치환 (토큰은 다른 확정 조건으로 거른 행 기준)."""
    where = dict(where or {})
    for k, v in list(where.items()):
        if isinstance(v, dict) and "ref" in v:
            where[k] = resolve_ref(ctx, v["ref"])[0]
    fixed = {k: v for k, v in where.items() if not (isinstance(v, str) and TOKEN_RE.match(v))}
    base_rows = [r for r in rows if _match(r, fixed, ctx)]
    for k, v in where.items():
        if isinstance(v, str) and TOKEN_RE.match(v):
            where[k] = resolve_token(base_rows, k, v)
    return where


def _fmt_where(where: dict[str, Any]) -> str:
    parts = []
    for k, v in (where or {}).items():
        if isinstance(v, dict) and "in_dataset" in v:
            parts.append(f"{k}∈{v['in_dataset']['dataset']}")
        elif isinstance(v, dict) and "in" in v:
            parts.append(f"{k}∈{{{','.join(map(str, v['in']))}}}")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def _get_path(obj: Any, path: str | None) -> Any:
    if not path:
        return obj
    for p in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(p)]
        elif isinstance(obj, dict):
            obj = obj.get(p)
        else:
            return None
    return obj


def resolve_ref(ctx: EvalContext, ref: dict[str, Any]) -> tuple[Any, str, Any]:
    """(값, 출처 문자열, 출처 상세)"""
    if "const" in ref:
        return ref["const"], "상수", None
    if "q" in ref:
        q = ref["q"]
        v, rows, ds = ctx.dataset(q["dataset"])
        q = {**q, "where": resolve_where(ctx, rows, q.get("where"))}
        sel = [r for r in rows if _match(r, q.get("where") or {}, ctx)]
        if q.get("order_by"):
            sel.sort(key=lambda r: (r.get(q["order_by"]) is None, r.get(q["order_by"])))
        col, agg = q.get("col"), q.get("agg", "first")
        vals = [r.get(col) for r in sel] if col else sel
        if agg != "list":
            vals = [x for x in vals if x is not None]
        if agg == "list":
            value: Any = vals
        elif agg == "count":
            value = len(sel)
        elif not vals:
            raise ResolveError(f"{q['dataset']}: 조건({_fmt_where(q.get('where') or {})})에 맞는 값 없음")
        elif agg == "sum":
            value = sum(formulas.D(x) for x in vals)
        elif agg == "max":
            value = max(vals)
        elif agg == "min":
            value = min(vals)
        else:
            value = vals[0]
        refs = sorted({r.get("src_ref") for r in sel if r.get("src_ref")})
        vers = sorted({r.get("__v") for r in sel if r.get("__v") is not None})
        files = sorted({r.get("__file") for r in sel if r.get("__file")})
        src = f"{ds.origin}.{ds.code} v{'+'.join(map(str, vers)) if vers else v.version}"
        if len(files) == 1:
            src += f" · {files[0]}"
        if refs and len(refs) <= 3:
            src += f"!{'/'.join(refs)}"
        src += f" · {_fmt_where(q.get('where') or {})}" + (f" · {col}" if col else "") + (f" ({agg} {len(sel)}행)" if agg in ("sum", "list", "count") else "")
        return value, src, {"dataset": ds.code, "version": v.version, "rows": len(sel)}
    if "metric" in ref:
        code = ref["metric"]
        field_ = ref.get("field", "value")
        oc = ctx.outcomes.get(code)
        if oc is not None:
            if oc.error:
                raise ResolveError(f"선행 지표 오류: {code}")
            val = oc.value if field_ == "value" else (oc.display if field_ == "display" else oc.extra.get(field_))
            return val, oc.calc_run_id, {"metric": code}
        last = ctx.session.execute(select(MetricValue).where(MetricValue.metric_code == code).order_by(MetricValue.created_at.desc()).limit(1)).scalar()
        if last is None or field_ != "value":
            raise ResolveError(f"지표 값 없음: {code}")
        return last.value, f"calc.metric_value({code})", {"metric": code}
    if "rule" in ref:
        rule = ctx.session.get(Rule, ref["rule"])
        if not rule:
            raise ResolveError(f"규칙 없음: {ref['rule']}")
        rv = ctx.session.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
        if not rv:
            raise ResolveError(f"규칙 버전 없음: {rule.code} v{rule.active_version}")
        return _get_path(rv.body, ref.get("path")), f"rule.{rule.code} v{rv.version}", {"rule": rule.code, "version": rv.version}
    if "setting" in ref:
        s = ctx.session.get(Setting, ref["setting"])
        if not s:
            raise ResolveError(f"설정 없음: {ref['setting']}")
        return _get_path(s.value, ref.get("path")), f"setting.{s.key}", None
    raise ResolveError(f"알 수 없는 참조: {ref}")


def _display_input(v: Any) -> str:
    if isinstance(v, list):
        return f"{len(v)}개 값"
    if isinstance(v, Decimal):
        if v == v.to_integral_value() and abs(v) >= 1000:
            return f"{int(v):,}"
        return f"{v.normalize():f}" if abs(v.as_tuple().exponent) < 12 else f"{v:.6f}"
    if isinstance(v, (int,)) and abs(v) >= 1000:
        return f"{v:,}"
    return str(v)


def _deps(m: Metric) -> set[str]:
    return {ref["metric"] for ref in (m.args or {}).values() if isinstance(ref, dict) and "metric" in ref}


def order_metrics(metrics: list[Metric]) -> list[Metric]:
    by = {m.code: m for m in metrics}
    out: list[Metric] = []
    seen: set[str] = set()
    visiting: set[str] = set()

    def visit(m: Metric):
        if m.code in seen:
            return
        if m.code in visiting:
            raise ResolveError(f"지표 순환 참조: {m.code}")
        visiting.add(m.code)
        for d in _deps(m):
            if d in by:
                visit(by[d])
        visiting.discard(m.code)
        seen.add(m.code)
        out.append(m)

    for m in sorted(metrics, key=lambda x: (x.sort, x.code)):
        visit(m)
    return out


def default_rounding(session: Session) -> str:
    s = session.get(Setting, "calc.rounding_default")
    return (s.value if s else None) or "HALF_UP"


def evaluate(ctx: EvalContext, metrics: list[Metric]) -> dict[str, MetricOutcome]:
    rounding_default = default_rounding(ctx.session)
    now = datetime.now(timezone.utc).isoformat()
    for m in order_metrics(metrics):
        inputs: dict[str, Any] = {}
        trace_inputs: list[dict[str, Any]] = []
        sources: list[Any] = []
        error = None
        try:
            for name, ref in (m.args or {}).items():
                if not isinstance(ref, dict):
                    ref = {"const": ref}
                value, src, detail = resolve_ref(ctx, ref)
                inputs[name] = value
                sources.append({"param": name, "source": src, **(detail or {})})
                trace_inputs.append({"key": name, "label": ref.get("label", name), "value": _display_input(value), "unit": ref.get("unit", ""), "source": src})
        except (ResolveError, formulas.FormulaError, KeyError, IndexError, TypeError) as exc:
            error = str(exc)
        rounding = m.rounding or rounding_default
        run, result, display = run_and_record(
            ctx.session,
            m.formula,
            inputs if error is None else {},
            metric_code=m.code,
            sources=sources,
            decimals=m.decimals,
            rounding=rounding,
            scale=m.scale,
            workflow_run_id=ctx.workflow_run_id,
        ) if error is None else _failed_run(ctx, m, error, sources)
        if error is None and run.error:
            error = run.error
        spec = formulas.REGISTRY.get(m.formula)
        prev = ctx.session.execute(
            select(MetricValue.display_value).where(MetricValue.metric_code == m.code).order_by(MetricValue.created_at.desc()).limit(1)
        ).scalar()
        data_origin = "simulated"
        used = [ctx.used_versions.get(s.get("dataset")) for s in sources if s.get("dataset")]
        if used and all(u and u.get("data_origin") == "actual" for u in used):
            data_origin = "actual"
        oc = MetricOutcome(
            code=m.code,
            label=m.label,
            formula=m.formula,
            value=result.value if result else None,
            display=display,
            extra=result.extra if result else {},
            calc_run_id=run.id,
            error=error,
            trace={
                "calcId": run.id,
                "formulaId": m.formula,
                "formulaVersion": spec.version if spec else 1,
                "expression": spec.expression if spec else m.formula,
                "inputs": trace_inputs,
                "executedAt": now,
                "note": f"표시 {m.decimals}자리 · {rounding}" + (f" · ÷{m.scale:g}" if m.scale else "") if m.decimals is not None else None,
            },
            figure_ids=list(m.figure_ids or [m.code]),
            unit=m.unit,
            decimals=m.decimals,
            data_origin=data_origin,
            previous=prev,
        )
        ctx.outcomes[m.code] = oc
        if not error:
            ctx.session.add(
                MetricValue(
                    metric_code=m.code,
                    value=oc.value,
                    display_value=display,
                    previous_value=prev,
                    calc_run_id=run.id,
                    workflow_run_id=ctx.workflow_run_id,
                )
            )
    return ctx.outcomes


def _failed_run(ctx: EvalContext, m: Metric, error: str, sources: list[Any]):
    from nhdip.models import CalcRun, new_id

    run = CalcRun(id=new_id(), formula_id=m.formula, metric_code=m.code, inputs={}, sources=sources, error=error, workflow_run_id=ctx.workflow_run_id)
    ctx.session.add(run)
    return run, None, None
