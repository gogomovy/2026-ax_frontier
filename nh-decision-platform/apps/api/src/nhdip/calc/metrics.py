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
    # 범위 실행(B.47 · 다지점) — 규칙 값 덮어쓰기 {규칙 코드: {키: 값}} 와 지표 값 저장 접미사(예: "@BR301").
    # 기본 범위(덮어쓰기 없음)는 이전과 똑같이 동작한다.
    rule_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    scope_suffix: str = ""

    def scoped(self, code: str) -> str:
        """지표 값 · 이력에 쓰는 코드 — 범위 실행이면 '<코드>@<범위>'."""
        return f"{code}{self.scope_suffix}" if self.scope_suffix else code

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
            if rows and not base_rows:
                # 자료는 있는데 다른 조건에 맞는 행이 없음(예: 연체 차주가 없는 지점 · B.47) — 토큰은 그대로 두어
                # 빈 선택(list → [], count → 0)이 되게 한다. 자료 자체가 없으면 아래에서 '값 없음' 오류 그대로.
                continue
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
        latest = {k: q["where"][k] for k, t in (ref["q"].get("where") or {}).items() if t == "$latest" and k in (q.get("where") or {}) and q["where"][k] != t}
        return value, src, {"dataset": ds.code, "version": v.version, "rows": len(sel), **({"latest": latest} if latest else {})}
    if "metric" in ref:
        code = ref["metric"]
        field_ = ref.get("field", "value")
        oc = ctx.outcomes.get(code)
        if oc is not None:
            if oc.error:
                raise ResolveError(f"선행 지표 오류: {code}")
            val = oc.value if field_ == "value" else (oc.display if field_ == "display" else oc.extra.get(field_))
            return val, oc.calc_run_id, {"metric": code}
        # 이 실행에서 계산하지 않은 지표 — 저장된 최근 값(범위 실행이면 그 범위 값 먼저)
        last = None
        for c in dict.fromkeys([ctx.scoped(code), code]):
            last = ctx.session.execute(select(MetricValue).where(MetricValue.metric_code == c).order_by(MetricValue.created_at.desc()).limit(1)).scalar()
            if last is not None:
                break
        if last is None or field_ != "value":
            raise ResolveError(f"지표 값 없음: {code}")
        return last.value, f"calc.metric_value({last.metric_code})", {"metric": code}
    if "rule" in ref:
        rule = ctx.session.get(Rule, ref["rule"])
        if not rule:
            raise ResolveError(f"규칙 없음: {ref['rule']}")
        rv = ctx.session.execute(select(RuleVersion).where(RuleVersion.rule_code == rule.code, RuleVersion.version == rule.active_version)).scalar()
        if not rv:
            raise ResolveError(f"규칙 버전 없음: {rule.code} v{rule.active_version}")
        body = rv.body
        over = ctx.rule_overrides.get(rule.code)
        if over and isinstance(body, dict):
            body = {**body, **over}  # 범위 실행 — 예: BRANCH_SCOPE.office_code 를 이번 범위 지점으로 (B.47)
        src = f"rule.{rule.code} v{rv.version}" + (f" · 범위 {over}" if over else "")
        return _get_path(body, ref.get("path")), src, {"rule": rule.code, "version": rv.version, **({"override": over} if over else {})}
    if "setting" in ref:
        s = ctx.session.get(Setting, ref["setting"])
        if not s:
            raise ResolveError(f"설정 없음: {ref['setting']}")
        return _get_path(s.value, ref.get("path")), f"setting.{s.key}", None
    raise ResolveError(f"알 수 없는 참조: {ref}")


def _display_input(v: Any) -> str:
    if isinstance(v, list):
        return f"{len(v)}개 값"
    if isinstance(v, dict):
        return f"항목 {len(v)}개"
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


UNIT_CHECK_DEFAULT = {"formulas": ["SUM", "DIFF", "MEAN", "MIN_OF", "GROWTH_RATE"], "mode": "block"}


def unit_check_policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "calc.unit_check")
    return {**UNIT_CHECK_DEFAULT, **(s.value if s and isinstance(s.value, dict) else {})}


def _origin_of(ctx: "EvalContext", sources: list[dict[str, Any]]) -> str:
    """데이터 성격 (B.32) — 데이터셋 버전 · 선행 지표(mref)의 성격을 모두 따른다. 섞이면 mixed, 원천이 없으면(상수 · 규칙) simulated."""
    origins: set[str] = set()
    for s in sources:
        if s.get("dataset"):
            u = ctx.used_versions.get(s["dataset"])
            origins.add((u or {}).get("data_origin") or "simulated")
        elif s.get("metric"):
            oc = ctx.outcomes.get(s["metric"])
            if oc is not None:
                origins.add(oc.data_origin)
    if not origins:
        return "simulated"
    if origins == {"actual"}:
        return "actual"
    if "actual" in origins or "mixed" in origins:
        return "mixed"
    return "simulated"


_UNIT_DIM: dict[str, tuple[str, float]] = {
    "%": ("rate", 1), "PCT": ("rate", 1), "%p": ("rate", 1), "PP": ("rate", 1), "pp": ("rate", 1), "bp": ("rate", 0.01),
    "원": ("money", 1), "KRW": ("money", 1), "백만원": ("money", 1e6), "KRW_MN": ("money", 1e6), "억원": ("money", 1e8),
    "십억원": ("money", 1e9), "KRW_BN": ("money", 1e9), "조원": ("money", 1e12), "KRW_TN": ("money", 1e12),
    "건": ("count", 1), "CNT": ("count", 1), "명": ("count", 1), "개": ("count", 1), "좌": ("count", 1),
}


def unit_conflict(units: dict[str, str]) -> bool:
    """입력 단위가 서로 맞지 않는지 — 차원(비율 · 금액 · 건수)이나 배율(백만원 vs 조원)이 다르면 True. 모르는 단위는 보지 않는다.
    %와 %p 는 같은 비율 차원으로 본다(증가율 − 안전 마진 등)."""
    dims = {_UNIT_DIM[u] for u in units.values() if u in _UNIT_DIM}
    return len(dims) > 1


def _input_units(ctx: "EvalContext", m: Metric) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, ref in (m.args or {}).items():
        if not isinstance(ref, dict):
            continue
        u = ref.get("unit")
        if not u and ref.get("metric") and ctx.outcomes.get(ref["metric"]) is not None:
            u = ctx.outcomes[ref["metric"]].unit
        if u:
            out[name] = str(u)
    return out


def evaluate(ctx: EvalContext, metrics: list[Metric]) -> dict[str, MetricOutcome]:
    rounding_default = default_rounding(ctx.session)
    unit_pol = unit_check_policy(ctx.session)
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
        warnings: list[str] = []
        # 단위 검사 (B.32) — 합 · 차 · 평균 등은 입력 단위가 같아야 한다 (설정 calc.unit_check)
        if error is None and m.formula in set(unit_pol.get("formulas") or []):
            units = _input_units(ctx, m)
            if unit_conflict(units):
                msg = "입력 단위 불일치 — " + ", ".join(f"{k}={v}" for k, v in units.items())
                if unit_pol.get("mode") == "block":
                    error = msg
                else:
                    warnings.append(msg)
        # 기준 시점 검사 — 입력마다 '$latest' 가 가리키는 기간이 다르면 경고
        latest: dict[str, set[str]] = {}
        for src_ in sources:
            for col, val in (src_.get("latest") or {}).items():
                latest.setdefault(col, set()).add(str(val))
        for col, vals in latest.items():
            if len(vals) > 1:
                warnings.append(f"기준 시점 불일치 — {col}: {', '.join(sorted(vals))} (데이터셋별 최신 기간이 다름)")
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
        # 직전 값 — 같은 범위끼리만 비교(다지점이면 지점마다 따로 · B.47)
        prev = ctx.session.execute(
            select(MetricValue.display_value).where(MetricValue.metric_code == ctx.scoped(m.code)).order_by(MetricValue.created_at.desc()).limit(1)
        ).scalar()
        data_origin = _origin_of(ctx, sources)
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
                **({"warnings": warnings} if warnings else {}),
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
                    metric_code=ctx.scoped(m.code),
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
