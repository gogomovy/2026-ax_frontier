"""지표 평가 엔진 — `cfg.metric` 정의(입력 참조 + 커널 수식)를 계산해 calc_run · metric_value 로 남긴다.

입력 참조 형식 (관리자 화면에서 편집)
  {"q": {"dataset": 자료, "where": {...}, "col": 컬럼, "agg": sum|first|list|count|max|min, "order_by": 컬럼}}
       자료: 데이터셋 코드 또는 업무 구성의 자료 이름(Phase O — 실행할 때 data.sources 가 찾는다)
       where 값: 스칼라(=) · {"in": [...]} · {"nin": [...]} · {"ne": v} · {"not": v} · {"path_endswith": "상위>이름"}
                 · {"startswith" | "endswith" | "contains": 글자} · {"ref": 참조} · {"in_dataset": {"dataset": 자료, "col": 컬럼, "where": {...}}}
                 (코드 비교는 글자로 · 모르는 연산자는 오류)
       기준일 열에는 기간 토큰을 쓴다 — 보관 기간에서 고르는 것: $latest · $prev(직전 보관 기간) · $prev-N · $earliest · $nearest-N(N개월 전에 가장 가까운 기간),
                 달 수로 세는 것: $latest-N(예: $latest-12 = 전년 동기) · $prev_year_end — 그 달이 없으면 최신보다 앞선 가장 가까운 보관 기간으로
                 대체하고(설정 calc.period_fallback) 계산 근거 · 화면 라벨에 실제 기간을 남긴다. 자세한 뜻은 resolve_token 참고
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

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from nhdip.data.datasets import current_rows
from nhdip.models import CalcRun, Dataset, Metric, MetricValue, Rule, RuleVersion, Setting, WorkflowRun, source

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
    # 기간 대체 — 입력(선행 지표 포함)이 가리키던 달이 없어 가장 가까운 보관 기간과 견줬으면
    # [{col, token, wanted, used, latest, months, wantedMonths, normalized?}] (normalized = 이 값은 이미 비교 기간에 맞춤)
    fallbacks: list[dict[str, Any]] = field(default_factory=list)
    # 비교 기간 맞춤 — {months, wantedMonths, token, used, params{이름: {from, to}}, goal{이름: {from, to}}} (없으면 None)
    align: dict[str, Any] | None = None
    goal: bool = False  # 경영목표 값 그대로(목표 규칙 경로의 VALUE) — 맞춤 · 화면 문구가 목표로 알아본다
    previous_run: str | None = None  # 직전 값의 계산 기록 — 변화 감지가 그때의 비교 기준과 견준다

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
    # 데이터셋별 가장 최근 버전 삭제 시각(지연 로딩) — 삭제된 자료로 계산한 지표 이력을 쓰지 않기 위해 (DEL-11)
    deleted_at: dict[str, datetime] | None = None
    rows: dict[str, tuple[Any, list[dict[str, Any]], Dataset]] = field(default_factory=dict)
    outcomes: dict[str, MetricOutcome] = field(default_factory=dict)
    used_versions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 범위 실행(B.47 · 다지점) — 규칙 값 덮어쓰기 {규칙 코드: {키: 값}} 와 지표 값 저장 접미사(예: "@BR301").
    # 기본 범위(덮어쓰기 없음)는 이전과 똑같이 동작한다.
    rule_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    scope_suffix: str = ""
    resolver: Any = None  # data.sources.Resolver — 자료 이름 → 데이터셋(실행 하나 동안 같은 답)
    period_fallback: bool | None = None  # 기간 대체(설정 calc.period_fallback) — 지연 로딩 · fallback_on
    period_align: str | None = None  # 비교 기간 맞춤(설정 calc.period_align) — 지연 로딩 · align_mode
    goal_rules: set[tuple[str, str]] | None = None  # 경영목표 규칙 경로(설정 goal.rule_links) — 지연 로딩 · goal_links

    def scoped(self, code: str) -> str:
        """지표 값 · 이력에 쓰는 코드 — 범위 실행이면 '<코드>@<범위>'."""
        return f"{code}{self.scope_suffix}" if self.scope_suffix else code

    def dataset(self, ref: str):
        """자료 참조(데이터셋 코드 또는 업무 구성의 자료 이름 — Phase O · BIZ-03) → (버전, 행, 정의).
        자료 이름은 실행할 때마다 지금 있는 정의에서 찾고, 그 자료의 코드용 열 별칭을 행에 더한다(원래 열은 그대로)."""
        if ref not in self.rows:
            from nhdip.data.sources import Resolver

            if self.resolver is None:
                self.resolver = Resolver(self.session)
            ds = self.resolver.resolve(ref)
            if not ds:
                raise ResolveError(f"데이터셋 없음: {ref}" + ("" if self.session.get(Dataset, ref) is not None else " (자료 대기 — 그 자료를 올리면 이어집니다)"))
            v, rows = current_rows(self.session, ds)
            if not v:
                raise ResolveError(f"확정된 버전 없음: {ref}")
            al = self.resolver.aliases(ref, ds)
            if al:
                rows = [{**r, **{k: r.get(c) for k, c in al.items() if k not in r}} for r in rows]
            self.rows[ref] = (v, rows, ds)
            self.used_versions[ds.code] = {"dataset": ds.code, "origin": ds.origin, "version": v.version, "version_id": v.id, "file": v.file_name, "data_origin": v.data_origin}
        return self.rows[ref]


def _key(v: Any) -> Any:
    """코드 비교용 값 — 정수 · 글자 코드가 섞여도 맞게 글자로(2001107820007 = '2001107820007'), 참거짓 · 빈 값은 그대로 (Phase O · BIZ-04)."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, Decimal) and v == v.to_integral_value():
        return str(int(v))
    return str(v).strip()


WHERE_OPS = ("in", "nin", "ne", "not", "in_dataset", "path_endswith", "startswith", "endswith", "contains", "ref")


def _path_parts(v: Any) -> list[str]:
    return [p.strip() for p in str(v or "").split(">") if p.strip()]


def _match(row: dict[str, Any], where: dict[str, Any], ctx: EvalContext) -> bool:
    for k, cond in (where or {}).items():
        val = row.get(k)
        if isinstance(cond, dict):
            op = next((o for o in WHERE_OPS if o in cond), None)
            if op == "in":
                if _key(val) not in {_key(x) for x in cond["in"]}:
                    return False
            elif op == "in_dataset":
                spec = cond["in_dataset"]
                _, rows, _ = ctx.dataset(spec["dataset"])
                allowed = {_key(r.get(spec["col"])) for r in rows if _match(r, spec.get("where") or {}, ctx)}
                if _key(val) not in allowed:
                    return False
            elif op == "ne":
                if _key(val) == _key(cond["ne"]):
                    return False
            elif op == "nin":
                # 목록에 없는 값만 (분석 에이전트 — 최댓값 · 최솟값에서 합계 · 기타 같은 집계 행 빼기)
                if _key(val) in {_key(x) for x in cond["nin"]}:
                    return False
            elif op == "not":
                if bool(val) == bool(cond["not"]):
                    return False
            elif op == "path_endswith":
                # 계층 경로('대출금>가계자금대출금')의 끝부분이 같은가 — 상위 항목 이름이 파일마다 몇 단계 위까지 적히는지 몰라도 맞게
                want = _path_parts(cond["path_endswith"])
                have = _path_parts(val)
                if not want or have[-len(want):] != want:
                    return False
            elif op == "ref":  # 안쪽 조건(in_dataset.where)의 참조 — 바깥 조건은 resolve_where 가 미리 바꾼다
                if str(val) != str(resolve_ref(ctx, cond["ref"])[0]):
                    return False
            elif op in ("startswith", "endswith", "contains"):
                s, t = str(val or ""), str(cond[op])
                if not (s.startswith(t) if op == "startswith" else s.endswith(t) if op == "endswith" else t in s):
                    return False
            else:
                # 모르는 조건은 모든 행을 맞게 두지 않는다 — 잘못 적은 구성이 조용히 전체 합계를 내지 않게
                raise ResolveError(f"알 수 없는 조건 연산자: {k}={cond}")
        elif str(val) != str(cond) if not isinstance(cond, bool) else bool(val) != cond:
            return False
    return True


TOKEN_RE = __import__("re").compile(r"^\$(latest|earliest|prev|prev_year_end|nearest)(?:-(\d+))?$")


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


def _month_index(value: Any) -> int | None:
    """YYYYMM · YYYY-MM-DD → 월 순번(연*12 + 월-1). 연월로 읽을 수 없으면 None."""
    s = str(value)
    if len(s) == 6 and s.isdigit():
        y, mo = int(s[:4]), int(s[4:])
    elif len(s) == 10 and s[4] == "-":
        y, mo = int(s[:4]), int(s[5:7])
    else:
        return None
    return y * 12 + (mo - 1) if 1 <= mo <= 12 else None


def periods_of(rows: list[dict[str, Any]], col: str) -> list[str]:
    """이 자료에 올라와 있는 기준일 값(오름차순 · 중복 제거) — '보관 기간'."""
    return sorted({str(r.get(col)) for r in rows if r.get(col) is not None})


def resolve_token(rows: list[dict[str, Any]], col: str, token: Any, *, fallback: bool = True) -> Any:
    """기간 토큰을 실제 기준일 값으로 (어느 기간으로 대체됐는지까지 알려면 resolve_token_info).

    보관 기간에서 고른다 — 올린 기준일이 띄어 있어도(예: 1월 · 8월만 올림) 비교가 된다:
      $latest      가장 늦은 기준일
      $earliest    가장 이른 기준일
      $prev        최신 바로 직전 기준일. 기간이 하나뿐이면 $latest 와 같다 — 첫 업로드에서 화면이 '갱신 실패'로 덮이지 않게
      $prev-N      최신에서 N번째 직전 기준일 (더 과거가 없으면 가장 이른 기준일)
      $nearest-N   'N개월 전'에 가장 가까운 보관 기간 (목표 이전을 먼저, 그런 기간이 없으면 가장 가까운 것)

    달 수로 센다 — 그 달이 보관돼 있으면 그 달:
      $latest-N      N개월 전 (예: $latest-12 = 전년 동기)
      $prev_year_end 최근 기간의 전년 12월
    그 달이 없으면(fallback · 설정 calc.period_fallback=nearest, 기본) 최신보다 앞선 보관 기간 중 그 달에 가장 가까운 기간으로 대체한다
    (같은 거리면 앞선 기간). 대체는 계산 근거(periodBasis) · 화면 라벨에 실제 기간으로 드러난다 — 라벨이 '전년 동기'라고 말하면서 다른 달과 견주지 않게.
    대신할 기간은 최신보다 그 달에 더 가까워야 한다(1월 · 8월이면 전년 동기 자리에 1월은 되지만 2년 전 자리에는 안 된다).
    그런 기간이 없으면(자기 자신 · 최근 달과 견주게 되면) 대체하지 않는다 — 맞는 행이 없어 오류('갱신 실패').
    fallback=False(설정 strict)면 대체하지 않는다.
    """
    return resolve_token_info(rows, col, token, fallback=fallback)[0]


FALLBACK_KINDS = ("latest", "prev_year_end")  # 달 수로 세는 토큰 — 그 달이 없을 때 가장 가까운 보관 기간으로 대체할 수 있는 것


def resolve_token_info(rows: list[dict[str, Any]], col: str, token: Any, *, fallback: bool = True) -> tuple[Any, str | None]:
    """(실제 기준일, 대체됐으면 원래 가리키던 기간 · 아니면 None) — 뜻은 resolve_token."""
    if not isinstance(token, str):
        return token, None
    m = TOKEN_RE.match(token)
    if not m:
        return token, None
    vals = periods_of(rows, col)
    if not vals:
        raise ResolveError(f"{col}: 값 없음")
    kind, n = m.group(1), int(m.group(2)) if m.group(2) else None
    if kind == "prev":
        return vals[max(len(vals) - 1 - max(n or 1, 1), 0)], None
    if kind == "nearest":
        if n is None:
            raise ResolveError(f"$nearest 는 개월 수가 필요합니다(예: $nearest-12) — {token}")
        target = _month_index(_shift(vals[-1], n))
        cand = [(mi, v) for v, mi in ((x, _month_index(x)) for x in vals) if mi is not None]
        if target is None or not cand:
            raise ResolveError(f"{col}: 기준일을 연월로 읽을 수 없어 {token} 을 쓸 수 없습니다")
        before = [c for c in cand if c[0] <= target]
        return (max(before)[1] if before else min(cand, key=lambda c: abs(c[0] - target))[1]), None
    base = vals[-1] if kind in FALLBACK_KINDS else vals[0]
    if kind == "prev_year_end":
        base = _shift(base, int(str(base).replace("-", "")[4:6]))  # 같은 해 1월의 한 달 전 = 전년 12월(YYYYMM · YYYY-MM-DD)
    want = _shift(base, n) if n else base
    if not fallback or kind not in FALLBACK_KINDS or want == vals[-1] or want in vals:
        return want, None
    wi, li = _month_index(want), _month_index(vals[-1])
    if wi is None or li is None:
        return want, None
    # 대신 견줄 수 있는 기간 — 최신보다 앞서고, 최신보다 가리키던 달에 더 가까운 것(그렇지 않으면 '전년 동기' 자리에 사실상 최근 달이 들어간다 —
    # 예: 1월 · 8월이면 전년 동기(작년 8월) 자리에 1월은 되지만, 2년 전(재작년 8월) 자리에 1월은 아니다)
    cand = [(mi, v) for v, mi in ((x, _month_index(x)) for x in vals) if mi is not None and mi < li and abs(mi - wi) < li - mi]
    same = [v for mi, v in cand if mi == wi]
    if same:
        return same[-1], None  # 같은 달의 다른 날짜(영업일 말일 등) — 같은 기간이라 대체로 보지 않는다
    if not cand:
        return want, None  # 견줄 앞선 기간이 없다 — 대체하지 않는다(맞는 행이 없어 오류 · 화면은 '갱신 실패')
    used = min(cand, key=lambda c: (abs(c[0] - wi), c[0] > wi))[1]
    return used, want


def token_name(token: str) -> str:
    """기간 토큰의 업무 이름 — 대체 안내 문구용(전년 동기 · 전년 말 · 전월 · N개월 전)."""
    m = TOKEN_RE.match(token or "")
    if not m:
        return str(token)
    kind, n = m.group(1), int(m.group(2)) if m.group(2) else 0
    if kind == "prev_year_end":
        return "전년 말"
    if kind == "latest" and n:
        return {1: "전월", 12: "전년 동기", 24: "2년 전 동기"}.get(n) or (f"{n // 12}년 전 동기" if n % 12 == 0 else f"{n}개월 전")
    return str(token)


def period_dot(value: Any) -> str:
    """202508 · 2025-08-31 → 2025.08 (안내 문구용)."""
    s = "".join(ch for ch in str(value or "") if ch.isdigit())
    return f"{s[:4]}.{s[4:6]}" if len(s) >= 6 else str(value)


def fallback_note(fb: dict[str, Any]) -> str:
    """대체 기록 한 건 → '전년 동기(2025.08) 자료가 없어 가장 가까운 기준일 2026.01 과 비교'."""
    return f"{token_name(str(fb.get('token') or ''))}({period_dot(fb.get('wanted'))}) 자료가 없어 가장 가까운 기준일 {period_dot(fb.get('used'))} 과 비교"


def span_months(latest: Any, wanted: Any, used: Any) -> dict[str, int]:
    """비교 기간(개월) — 최신에서 원래 가리키던 기간까지(wantedMonths) · 실제로 견준 기간까지(months). 연월로 읽을 수 없으면 빈 값."""
    li, wi, ui = _month_index(latest), _month_index(wanted), _month_index(used)
    if li is None or wi is None or ui is None:
        return {}
    return {"months": li - ui, "wantedMonths": li - wi}


def span_of(fallbacks: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """기간 대체 기록 중 비교 기간이 원래와 다른 것(맞춤 대상) — 여럿이면 원래 비교 기간이 가장 긴 것.
    이미 비교 기간에 맞춘 값(normalized — 기간 인자 · 목표를 환산한 결과)은 다시 맞추지 않는다."""
    best: dict[str, Any] | None = None
    for f in fallbacks or []:
        if not isinstance(f, dict) or f.get("normalized"):
            continue
        m, w = f.get("months"), f.get("wantedMonths")
        if isinstance(m, int) and isinstance(w, int) and m > 0 and w > 0 and m != w and (best is None or w > best["wantedMonths"]):
            best = f
    return best


def align_mode_of(session: Session) -> str:
    """비교 기간 맞춤 — 설정 calc.period_align: prorate(기본 · 기간 인자 · 경영목표를 실제 비교 기간에 맞춰 환산) | off(맞추지 않고 목표 판정 보류)."""
    s = session.get(Setting, "calc.period_align")
    v = s.value if s is not None else None
    mode = v.get("mode") if isinstance(v, dict) else v
    return "off" if str(mode if mode is not None else "prorate").strip().lower() in ("off", "none", "false", "hold") else "prorate"


def align_mode(ctx: "EvalContext | None") -> str:
    """align_mode_of — 실행 하나 동안 같은 답."""
    if ctx is None or getattr(ctx, "session", None) is None:
        return "prorate"
    if getattr(ctx, "period_align", None) is None:
        ctx.period_align = align_mode_of(ctx.session)
    return ctx.period_align


def goal_links(ctx: "EvalContext") -> set[tuple[str, str]]:
    """경영목표 값이 사는 규칙 경로 {(규칙, 경로)} — 설정 goal.rule_links(목표 확정 · 판정이 쓰는 같은 연결). 실행 하나 동안 같은 답."""
    if ctx.goal_rules is None:
        s = ctx.session.get(Setting, "goal.rule_links")
        v = s.value if s is not None and isinstance(s.value, dict) else {}
        ctx.goal_rules = {(str(x["rule"]), str(x["path"])) for x in v.values() if isinstance(x, dict) and x.get("rule") and x.get("path")}
    return ctx.goal_rules


def is_goal_ref(ctx: "EvalContext", ref: Any, _depth: int = 0) -> bool:
    """입력이 경영목표 값인가 — 목표 규칙 경로이거나, 그 값을 그대로 쓰는 지표(VALUE)."""
    if not isinstance(ref, dict) or _depth > 3:
        return False
    if ref.get("rule") and ref.get("path"):
        return (str(ref["rule"]), str(ref["path"])) in goal_links(ctx)
    code = ref.get("metric")
    if not code or ref.get("field") not in (None, "value"):
        return False
    oc = ctx.outcomes.get(code)
    if oc is not None:
        return oc.goal
    m = ctx.session.get(Metric, code)
    args = list((m.args or {}).values()) if m is not None else []
    return m is not None and m.formula == "VALUE" and len(args) == 1 and is_goal_ref(ctx, args[0], _depth + 1)


def ratio_text(span: dict[str, Any]) -> str:
    return f"{span['months']}/{span['wantedMonths']}"


def align_note(label: str, before: Any, after: Any, span: dict[str, Any], what: str) -> str:
    """'경영목표 7 → 4.08 (비교 기간 7개월에 맞춰 연 목표 × 7/12)'."""
    return f"{label} {_display_input(before)} → {_display_input(after)} ({what} — 비교 기간 {span['months']}개월에 맞춰 × {ratio_text(span)})"


def fallback_on(ctx: "EvalContext | None") -> bool:
    """기간 대체를 쓰는가 — 설정 calc.period_fallback: nearest(기본) | strict. 실행 하나 동안 같은 답."""
    if ctx is None or getattr(ctx, "session", None) is None:
        return True
    if getattr(ctx, "period_fallback", None) is None:
        s = ctx.session.get(Setting, "calc.period_fallback")
        v = s.value if s is not None else None
        mode = v.get("mode") if isinstance(v, dict) else v
        ctx.period_fallback = str(mode or "nearest").strip().lower() != "strict"
    return ctx.period_fallback


def anchor_dataset(ctx: "EvalContext", ref: dict[str, Any]) -> str | None:
    """규칙 · 설정이 기간 토큰을 주면 그 토큰을 어느 자료의 보관 기간에서 고를지 — 본문의 '<경로>_source'(자료 이름).

    기준시점은 분석 하나에 하나여야 한다. 자료마다 올라온 기간이 다를 수 있으므로, 기준 자료를 정해 두면
    그 자료를 쓰지 않는 지표 · 화면 라벨도 같은 기준시점을 쓴다(라벨이 말하는 기간과 실제 견준 기간이 어긋나지 않게).
    """
    if not (ref.get("rule") or ref.get("setting")) or not ref.get("path"):
        return None
    src = resolve_ref(ctx, {**{k: ref[k] for k in ("rule", "setting") if k in ref}, "path": f"{ref['path']}_source"})[0]
    return src.strip() if isinstance(src, str) and src.strip() else None


def resolve_period(ctx: "EvalContext", value: Any, *, anchor: str | None, rows: list[dict[str, Any]], col: str, notes: dict[str, dict[str, Any]] | None = None) -> Any:
    """기간 토큰을 실제 기준일로 — 기준 자료(anchor)가 정해져 있으면 그 자료의 보관 기간에서 고른다.
    notes 를 주면 대체가 일어났을 때 {col: {token, wanted, used}} 를 남긴다(계산 근거 · 화면 라벨용)."""
    if not (isinstance(value, str) and TOKEN_RE.match(value)):
        return value
    if anchor:
        _, a_rows, a_ds = ctx.dataset(anchor)
        rows, col_used = a_rows, a_ds.as_of_column or col
    else:
        col_used = col
    used, wanted = resolve_token_info(rows, col_used, value, fallback=fallback_on(ctx))
    if wanted is not None and notes is not None:
        latest = periods_of(rows, col_used)[-1]
        notes[col] = {"token": value, "wanted": wanted, "used": used, "latest": latest, **span_months(latest, wanted, used)}
    return used


def resolve_where(ctx: "EvalContext", rows: list[dict[str, Any]], where: dict[str, Any] | None, notes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """조건의 토큰·참조를 확정 값으로 치환 (토큰은 다른 확정 조건으로 거른 행 기준). notes — 기간 대체 기록(resolve_period)."""
    where = dict(where or {})
    anchors: dict[str, str] = {}
    for k, v in list(where.items()):
        if isinstance(v, dict) and "ref" in v:
            where[k] = resolve_ref(ctx, v["ref"])[0]
            if isinstance(where[k], str) and TOKEN_RE.match(where[k]):
                a = anchor_dataset(ctx, v["ref"])
                if a:
                    anchors[k] = a
    fixed = {k: v for k, v in where.items() if not (isinstance(v, str) and TOKEN_RE.match(v))}
    base_rows = [r for r in rows if _match(r, fixed, ctx)]
    for k, v in where.items():
        if isinstance(v, str) and TOKEN_RE.match(v):
            if k in anchors:
                # 기준 자료가 정해진 토큰 — 이 질의의 행이 아니라 그 자료의 보관 기간에서 고른다.
                # 고른 기간이 이 자료에 없으면 맞는 행이 없어 '값 없음' 오류가 나고 화면은 '갱신 실패'로 표시된다(조용히 다른 달과 견주지 않게)
                where[k] = resolve_period(ctx, v, anchor=anchors[k], rows=base_rows, col=k, notes=notes)
                continue
            if rows and not base_rows:
                # 자료는 있는데 다른 조건에 맞는 행이 없음(예: 연체 차주가 없는 지점 · B.47) — 토큰은 그대로 두어
                # 빈 선택(list → [], count → 0)이 되게 한다. 자료 자체가 없으면 아래에서 '값 없음' 오류 그대로.
                continue
            where[k] = resolve_period(ctx, v, anchor=None, rows=base_rows, col=k, notes=notes)
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


HISTORY_SCAN = 8  # 저장된 지표 값을 거슬러 볼 최대 건수 — 삭제된 자료로 계산한 값을 건너뛰고 쓸 만한 값을 찾는 범위


def _deleted_at(ctx: EvalContext) -> dict[str, datetime]:
    """데이터셋 코드 → 가장 최근에 버전을 삭제한 시각. 실행당 한 번만 읽는다."""
    if ctx.deleted_at is None:
        out: dict[str, datetime] = {}
        for origin in ("bank", "ext"):
            t = source(origin)
            q = select(t.version.dataset_code, func.max(t.version.deleted_at)).where(t.version.status == "deleted").group_by(t.version.dataset_code)
            for code, at in ctx.session.execute(q):
                if at is not None and (code not in out or at > out[code]):
                    out[code] = at
        ctx.deleted_at = out
    return ctx.deleted_at


def _from_deleted_data(ctx: EvalContext, mv: MetricValue) -> bool:
    """이 지표 값이, 이후에 버전이 삭제된 데이터셋으로 계산됐는가(계산 기록의 입력 출처 기준).
    삭제 시각 이전에 계산한 값은 어느 버전이 삭제됐든 쓰지 않는다 — 어떤 버전이 입력이었는지 기록하지 않은 경우까지 안전하게."""
    gone = _deleted_at(ctx)
    if not gone or not mv.calc_run_id:
        return False
    run = ctx.session.get(CalcRun, mv.calc_run_id)
    if run is None:
        return False
    return any(isinstance(s, dict) and s.get("dataset") in gone and mv.created_at < gone[s["dataset"]] for s in run.sources or [])


def merge_fallbacks(sources: list[Any]) -> list[dict[str, Any]]:
    """입력 출처들의 기간 대체 기록을 모은다(같은 토큰 · 같은 대체는 한 번)."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for s in sources:
        for f in (s.get("fallback") or []) if isinstance(s, dict) else []:
            if not isinstance(f, dict):
                continue
            key = (str(f.get("token")), str(f.get("wanted")), str(f.get("used")))
            if key not in seen:
                seen.add(key)
                out.append({k: f[k] for k in BASIS_KEYS if f.get(k) is not None})
            elif f.get("normalized"):
                next(x for x in out if (str(x.get("token")), str(x.get("wanted")), str(x.get("used"))) == key)["normalized"] = True
    return out


BASIS_KEYS = ("col", "token", "wanted", "used", "latest", "months", "wantedMonths", "normalized")
BASIS_PARAM = "_basis"  # 계산 기록 입력 출처에 남기는 결과의 비교 기준(맞춤 표시 포함) — 저장된 값을 다른 지표가 쓸 때 그대로 따라간다


def basis_of_sources(sources: list[Any]) -> list[dict[str, Any]]:
    """계산 기록 입력 출처 → 그 결과의 비교 기준. 결과 기록(_basis)이 있으면 그것, 없으면(이전 기록) 입력에서 모은다."""
    for s in sources or []:
        if isinstance(s, dict) and s.get("param") == BASIS_PARAM:
            return [dict(f) for f in s.get("fallback") or [] if isinstance(f, dict)]
    return merge_fallbacks(list(sources or []))


def run_basis(session: Session, calc_run_id: str | None) -> list[dict[str, Any]]:
    run = session.get(CalcRun, calc_run_id) if calc_run_id else None
    return basis_of_sources(list(run.sources or [])) if run is not None else []


def _stored_fallbacks(ctx: EvalContext, mv: MetricValue) -> list[dict[str, Any]]:
    """저장된 지표 값이 기간을 대체해 계산됐는지 — 그 계산 기록에서."""
    return run_basis(ctx.session, mv.calc_run_id)


def resolve_ref(ctx: EvalContext, ref: dict[str, Any]) -> tuple[Any, str, Any]:
    """(값, 출처 문자열, 출처 상세)"""
    if "const" in ref:
        return ref["const"], "상수", None
    if "q" in ref:
        q = ref["q"]
        v, rows, ds = ctx.dataset(q["dataset"])
        notes: dict[str, dict[str, Any]] = {}
        q = {**q, "where": resolve_where(ctx, rows, q.get("where"), notes)}
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
        # 기간 토큰이 실제로 어느 기준일로 풀렸는지 — 계산 근거에 남겨 어떤 두 시점을 견줬는지 보이게 한다
        picked = {k: (t, q["where"][k]) for k, t in (ref["q"].get("where") or {}).items()
                  if isinstance(t, str) and TOKEN_RE.match(t) and k in (q.get("where") or {}) and q["where"][k] != t}
        periods = {f"{k}@{t}": val for k, (t, val) in picked.items()}
        latest = {k: val for k, (t, val) in picked.items() if t == "$latest"}
        # 기간 대체(그 달이 없어 가장 가까운 보관 기간과 견줌) — 이 지표를 쓰는 지표 · 화면 라벨까지 따라간다
        fallback = [{"col": k, **n} for k, n in notes.items()]
        return value, src, {"dataset": ds.code, "version": v.version, "rows": len(sel),
                            **({"periods": periods} if periods else {}), **({"latest": latest} if latest else {}), **({"fallback": fallback} if fallback else {})}
    if "metric" in ref:
        code = ref["metric"]
        field_ = ref.get("field", "value")
        oc = ctx.outcomes.get(code)
        if oc is not None:
            if oc.error:
                raise ResolveError(f"선행 지표 오류: {code}")
            val = oc.value if field_ == "value" else (oc.display if field_ == "display" else oc.extra.get(field_))
            return val, oc.calc_run_id, {"metric": code, **({"fallback": list(oc.fallbacks)} if oc.fallbacks else {})}
        # 이 실행에서 계산하지 않은 지표 — 저장된 최근 값(범위 실행이면 그 범위 값 먼저).
        # 이미 삭제된 자료로 계산한 값은 건너뛴다 — 삭제한 자료의 수치가 다른 지표의 입력으로 되살아나지 않게 (DEL-11)
        last, skipped = None, 0
        for c in dict.fromkeys([ctx.scoped(code), code]):
            for mv in ctx.session.execute(select(MetricValue).where(MetricValue.metric_code == c).order_by(MetricValue.created_at.desc()).limit(HISTORY_SCAN)).scalars():
                if _from_deleted_data(ctx, mv):
                    skipped += 1
                    continue
                last = mv
                break
            if last is not None:
                break
        if last is None or field_ != "value":
            raise ResolveError(f"지표 값 없음: {code}" + (" (삭제된 자료로 계산한 값은 쓰지 않습니다 — 다시 계산되면 채워집니다)" if skipped and last is None else ""))
        fb = _stored_fallbacks(ctx, last)
        return last.value, f"calc.metric_value({last.metric_code})", {"metric": code, **({"fallback": fb} if fb else {})}
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
        except (ResolveError, formulas.FormulaError, KeyError, IndexError, TypeError, ArithmeticError) as exc:
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
        # 기준 시점 검사 — 같은 기간 토큰이 입력마다 다른 기준일을 가리키면 경고(자료별로 올라온 기간이 달라서 생긴다)
        seen: dict[str, set[str]] = {}
        for src_ in sources:
            for key, val in (src_.get("periods") or {}).items():
                seen.setdefault(key, set()).add(str(val))
        for key, vals in seen.items():
            if len(vals) > 1:
                col, _, tok = key.partition("@")
                warnings.append(f"기준 시점 불일치 — {col} {tok}: {', '.join(sorted(vals))} (자료별로 올라온 기간이 다름)")
        # 기간 대체 — 화면이 '전년 동기'라고 말하지 않고 실제로 견준 기간을 쓰게(build_views → Figure.basis)
        fallbacks = merge_fallbacks(sources) if error is None else []
        warnings.extend(fallback_note(f) for f in fallbacks)
        # 비교 기간 맞춤(PER-05) — 실제로 견준 기간이 원래와 다르면 기간 인자(CAGR 기간)와 경영목표(목표 대비 이탈 · 달성률)를 그 기간에 맞춘다
        align = None
        if error is None and fallbacks:
            fallbacks, align = _align_inputs(ctx, m, inputs, sources, trace_inputs, fallbacks, warnings)
        if error is None and fallbacks:
            # 결과의 비교 기준(맞춤 표시 포함) — 저장된 값을 다른 지표 · 다음 실행의 변화 감지가 읽을 때 그대로 따라간다(대체가 없으면 남기지 않는다)
            sources.append({"param": BASIS_PARAM, "source": "비교 기준", "fallback": fallbacks, **({"align": align} if align else {})})
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
        # 실패한 실행이 남긴 값은 기준으로 삼지 않는다 — 다시 시도(재실행)가 '변화 없음'으로 보고 변화 감지를 놓치지 않게
        prev_row = ctx.session.execute(
            select(MetricValue.display_value, MetricValue.calc_run_id)
            .where(
                MetricValue.metric_code == ctx.scoped(m.code),
                ~exists().where(WorkflowRun.id == MetricValue.workflow_run_id, WorkflowRun.status == "failed"),
            )
            .order_by(MetricValue.created_at.desc())
            .limit(1)
        ).first()
        prev, prev_run = (prev_row[0], prev_row[1]) if prev_row is not None else (None, None)
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
                **({"periodBasis": fallbacks} if fallbacks else {}),
                **({"periodAlign": align} if align else {}),
            },
            figure_ids=list(m.figure_ids or [m.code]),
            unit=m.unit,
            decimals=m.decimals,
            data_origin=data_origin,
            previous=prev,
            fallbacks=fallbacks,
            align=align,
            goal=m.formula == "VALUE" and len(m.args or {}) == 1 and is_goal_ref(ctx, next(iter((m.args or {}).values()))),
            previous_run=prev_run,
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


def _data_ref(ref: Any) -> bool:
    """자료 · 다른 지표에서 온 입력인가 — 그런 값은 비교 기간 맞춤에서 바꾸지 않는다(기간 인자는 상수 · 규칙 값만)."""
    return isinstance(ref, dict) and ("q" in ref or "metric" in ref)


def _align_inputs(ctx: EvalContext, m: Metric, inputs: dict[str, Any], sources: list[Any], trace_inputs: list[dict[str, Any]],
                  fallbacks: list[dict[str, Any]], warnings: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """실제로 견준 기간이 원래와 다를 때(예: 전년 동기 12개월 → 7개월) 그 기간에 맞춘다 — 설정 calc.period_align.

    · 기간 길이 인자(수식 period_params — CAGR 기간)는 실제 비교 기간으로 바꾼다 → 결과는 '맞춘 값'(normalized)이라 뒤에서 다시 맞추지 않는다.
    · 실적과 경영목표를 견주는 수식(goal_align — 목표 대비 이탈 · 달성률)은 목표 입력을 그 기간에 비례 환산한다(연 목표 × 7/12 —
      화면 목표 경로와 같은 '경과월 ÷ 12' 규칙). 비교 대상이 목표인지는 설정 goal.rule_links 로 안다(목표 확정 · 판정과 같은 연결).
    계산 근거에 원래 값 · 환산 값 · 비율이 남는다. (맞춘 비교 기준, 맞춤 기록 | None)"""
    span = span_of(fallbacks)
    spec = formulas.REGISTRY.get(m.formula)
    if span is None or spec is None or align_mode(ctx) != "prorate":
        return fallbacks, None
    ratio = Decimal(span["months"]) / Decimal(span["wantedMonths"])
    args = {k: (v if isinstance(v, dict) else {"const": v}) for k, v in (m.args or {}).items()}
    done: dict[str, dict[str, dict[str, str]]] = {"params": {}, "goal": {}}

    def scale(name: str, kind: str, what: str) -> None:
        before = formulas.D(inputs[name])
        after = before * ratio
        inputs[name] = after
        done[kind][name] = {"from": str(before), "to": str(after)}
        label = args[name].get("label", name)
        for t in trace_inputs:
            if t["key"] == name:
                t["value"] = _display_input(after)
                t["label"] = f"{label} (비교 기간 {span['months']}개월 환산)"
                t["source"] = f"{t['source']} · {_display_input(before)} × {ratio_text(span)}"
        for s in sources:
            if isinstance(s, dict) and s.get("param") == name:
                s["aligned"] = {"from": str(before), "to": str(after), "ratio": ratio_text(span)}
        warnings.append(align_note(label, before, after, span, what))

    try:
        for name in spec.period_params:
            if name in inputs and not _data_ref(args.get(name)):
                scale(name, "params", "기간")
        if spec.goal_align:
            goals = [n for n in inputs if is_goal_ref(ctx, args.get(n))]
            # 목표끼리 견주는 수식(둘 다 목표)이나 목표만 있는 수식은 맞추지 않는다 — 실적 쪽이 있어야 비교 기간이 뜻을 가진다
            if goals and len(goals) < len(inputs):
                for name in goals:
                    scale(name, "goal", "경영목표")
    except (formulas.FormulaError, ArithmeticError, TypeError):
        return fallbacks, None
    if not done["params"] and not done["goal"]:
        return fallbacks, None
    align = {"months": span["months"], "wantedMonths": span["wantedMonths"], "token": span.get("token"), "used": span.get("used"), "wanted": span.get("wanted"),
             **{k: v for k, v in done.items() if v}}
    # 맞춘 값 — 이 지표를 쓰는 지표 · 목표 판정 · 화면 문구가 다시 맞추지 않게(비교 기준 표시는 그대로 따라간다)
    return [{**f, "normalized": True} for f in fallbacks], align


def _failed_run(ctx: EvalContext, m: Metric, error: str, sources: list[Any]):
    from nhdip.models import CalcRun, new_id

    run = CalcRun(id=new_id(), formula_id=m.formula, metric_code=m.code, inputs={}, sources=sources, error=error, workflow_run_id=ctx.workflow_run_id)
    ctx.session.add(run)
    return run, None, None
