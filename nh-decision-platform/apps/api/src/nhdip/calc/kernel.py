"""커널 실행 · 반올림 · calc_run 기록."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any

import numpy
import scipy
import sklearn
from sqlalchemy.orm import Session

from nhdip.models import CalcRun, new_id

from . import formulas
from .formulas import FormulaError

ROUNDING = {"HALF_UP": ROUND_HALF_UP, "HALF_EVEN": ROUND_HALF_EVEN, "DOWN": ROUND_DOWN, "UP": ROUND_UP}
LIB_VERSIONS = {
    "decimal": "decimal",
    "numpy": f"numpy {numpy.__version__}",
    "scipy": f"scipy {scipy.__version__}",
    "scikit-learn": f"scikit-learn {sklearn.__version__}",
}


@dataclass
class CalcResult:
    formula_id: str
    formula_version: int
    expression: str
    value: Decimal | None
    extra: dict[str, Any] = field(default_factory=dict)
    library: str = "decimal"


def execute(formula_id: str, inputs: dict[str, Any]) -> CalcResult:
    spec = formulas.get(formula_id)
    unknown = set(inputs) - set(spec.params)
    if unknown:
        raise FormulaError(f"{formula_id}: 알 수 없는 입력 {sorted(unknown)}")
    out = spec.fn(**inputs)
    extra: dict[str, Any] = {}
    if isinstance(out, dict):
        extra = {k: v for k, v in out.items() if k != "value"}
        value = out.get("value")
    else:
        value = out
    value = formulas.D(value) if value is not None else None
    return CalcResult(spec.id, spec.version, spec.expression, value, extra, LIB_VERSIONS.get(spec.library, spec.library))


def round_display(value: Decimal | None, decimals: int | None, rounding: str | None = "HALF_UP", scale: float | None = None) -> Decimal | None:
    if value is None:
        return None
    v = value
    if scale:
        v = v / formulas.D(scale)
    if decimals is None:
        return v
    mode = ROUNDING.get((rounding or "HALF_UP").upper(), ROUND_HALF_UP)
    return v.quantize(Decimal(1).scaleb(-decimals), rounding=mode)


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if hasattr(v, "item"):
        return v.item()
    return v


def run_and_record(
    session: Session,
    formula_id: str,
    inputs: dict[str, Any],
    *,
    metric_code: str | None = None,
    sources: list[Any] | None = None,
    decimals: int | None = None,
    rounding: str | None = None,
    scale: float | None = None,
    workflow_run_id: str | None = None,
) -> tuple[CalcRun, CalcResult | None, Decimal | None]:
    """수식을 실행하고 calc_run 을 남긴다. 실패도 기록한다(오류 내용 포함)."""
    run = CalcRun(
        id=new_id(),
        formula_id=formula_id,
        metric_code=metric_code,
        inputs=_jsonable(inputs),
        sources=_jsonable(sources or []),
        decimals=decimals,
        rounding=rounding,
        workflow_run_id=workflow_run_id,
    )
    result: CalcResult | None = None
    display: Decimal | None = None
    try:
        result = execute(formula_id, inputs)
        display = round_display(result.value, decimals, rounding, scale)
        run.formula_version = result.formula_version
        run.value = result.value
        run.display_value = display
        run.result = _jsonable({"value": result.value, **result.extra})
        run.library = result.library
    except (FormulaError, ArithmeticError, TypeError) as exc:
        run.error = str(exc)
    session.add(run)
    return run, result, display
