"""화면 틀(template) · 서식 문구(Tpl) — Phase I · 설계 §25.4 · Q138.

0세대 화면 산출물은 구조 · 라벨 · 수치 id 만 갖고 값이 없다(`to_template`). 숫자 · 기간이 들어가는 평문 필드는
`<필드>Tpl` 에 표식으로 두고, 워크플로 `build_views` 가 계산 결과로 `<필드>` 를 채운다(`render_templates`).

표식
  [[fig:ID]]            수치 표시(값 · 자릿수 · 단위) — 값이 없으면 '–'
  [[fig:ID|signed]]     부호 붙임(+3.49%)      [[fig:ID|num]]  단위 없는 숫자      [[fig:ID|verdict]]  판정 문구(BAND · 검정)
  [[fig:ID|abs]]        절댓값                [[fig:ID|unit]]  단위만
  [[ym:데이터셋:토큰|형식]]  그 자료의 기간(`$latest` · `$prev` · `$earliest` · `$latest-12` · `$nearest-12` …) — dot(2026.08) · month(8월) · year(2026) · ym · date(2026.08.31) · kor(2026년 8월)
  [[rule:코드.경로|형식]]   규칙 값 — d0~d3(소수 자릿수) · +d1(부호) · pct0(0.95 → 95%) · 기간 형식(dot · month …) 또는 그대로
  [[if:A>B|참 문구|거짓 문구|값 없음 문구]]  수치 비교로 문구를 고른다 — A · B 는 수치 id 또는 숫자, 비교 > < >= <= = != (값이 없으면 넷째 문구, 없으면 빈 문구)
  [[at:경로]]            같은 산출물의 값(예: office.name — 바인딩이 채운 영업점 이름)
수치는 산출물들에 이미 반영된 Figure 값(id 별)으로 렌더한다 — 다른 워크플로가 계산한 수치도 쓸 수 있다.

서술 필드(statement · judgement · summary)는 [[fig:ID]] 표식을 그대로 둔다 — 화면이 수치 칩으로 그리고, 검증(critic)이 표식으로 수치 출처를 확인한다.
에이전트가 쓴 문장(`<필드>By: "llm"`)은 그 문장이 기대는 수치가 바뀌기 전까지 규칙 문장으로 되돌리지 않는다(`refresh`).
"""
from __future__ import annotations

import copy
import re
from typing import Any, Iterable

from nhdip.views.store import find_paths

DASH = "–"
TPL = "Tpl"
FIG_DROP = ("calc", "sourceRef", "dataOrigin", "stale", "staleReason", "verdict", "severity")
# 사람이 만드는 내용(다른 부서 요청 · 검토 대기)은 시드가 만들지 않는다 — 사용자 요청만 (Q135)
DEMO_ARTIFACTS: dict[str, Any] = {"report_requests": [], "review_queue": []}
DEMO_FIELDS: dict[str, list[str]] = {"hq_dashboard": ["requests"]}
TOKEN = re.compile(r"\[\[(fig|ym|rule):([^\]|]+)(?:\|([a-z0-9+]+))?\]\]")
IF_TOKEN = re.compile(r"\[\[if:([^\]|]+)\|([^\]|]*)\|([^\]|]*)(?:\|([^\]|]*))?\]\]")
AT_TOKEN = re.compile(r"\[\[at:([A-Za-z0-9_.]+)\]\]")
IF_EXPR = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(>=|<=|!=|>|<|=)\s*([A-Za-z0-9_.\-]+)\s*$")
# 화면이 [[fig:ID]] 를 수치 칩으로 그리는 서술 필드 — 서식 문구를 렌더할 때 수치 표식은 남긴다
KEEP_FIG_FIELDS = frozenset({"statement", "judgement", "summary"})
BY = "By"  # `<필드>By` = 그 필드를 쓴 주체(llm) — 규칙 문장(서식 문구)이 덮어쓰지 않게
DOC_EVIDENCE_KEYS = ("doc",)  # 문서 인용 근거(실행 때 올라온 문서에서 붙인다) — 화면 틀에는 두지 않는다
UNIT_LABELS = {"KRW_MN": "백만원", "KRW_BN": "억원", "KRW_TN": "조원", "PCT": "%", "PP": "%p", "CNT": "건", "RATIO": "", "NONE": ""}


def is_figure(d: Any) -> bool:
    return isinstance(d, dict) and "id" in d and "label" in d and "unit" in d and "value" in d


def _walk(obj: Any, fn) -> None:
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            fn(o)
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)


# ═════════════════════════ 바인딩 대상 ═════════════════════════
def binding_targets(payload: Any, path: str) -> list[tuple[str, str]]:
    """바인딩 경로 → [(점 경로, 필드)] — 'table:캡션' · 'table_note:캡션' · 'chart:제목' · 'series:키' · 점 표기 경로.

    캡션 · 제목이 서식 문구(Tpl)로 바뀌어도 찾을 수 있게 처음 캡션(`bindKey`)으로도 맞춘다."""
    def same(d: dict[str, Any], fld: str, want: str) -> bool:
        return d.get(fld) == want or d.get("bindKey") == want

    if path.startswith("table:"):
        cap = path[6:]
        return [(p, "rows") for p in find_paths(payload, lambda d: same(d, "caption", cap) and "rows" in d)]
    if path.startswith("table_note:"):
        cap = path[11:]
        return [(p, "note") for p in find_paths(payload, lambda d: same(d, "caption", cap) and "rows" in d)]
    if path.startswith("chart:"):
        title = path[6:]
        return [(p, "series") for p in find_paths(payload, lambda d: same(d, "title", title) and "series" in d)]
    if path.startswith("series:"):
        key = path[7:]
        return [(p, "points") for p in find_paths(payload, lambda d: d.get("key") == key and "points" in d)]
    parts = path.rsplit(".", 1)
    return [(parts[0], parts[1])] if len(parts) == 2 else [("", path)]


def get_parent(payload: Any, parent: str) -> Any:
    obj = payload
    for p in [x for x in parent.split(".") if x]:
        obj = obj[int(p)] if isinstance(obj, list) else obj[p]
    return obj


# 대상 자체가 표 · 차트 · 계열 객체인 경로 — 점 표기 경로(예: 'corporate.yearly')는 부모가 여러 수치를 품은 큰 객체라 표시를 달지 않는다
STALE_MARK_PREFIXES = ("table:", "table_note:", "chart:", "series:")


def _has_content(obj: dict[str, Any]) -> bool:
    """표(rows) · 차트(series → points) · 계열(points)에 이전 값이 있는가. 해당 키가 없는 객체는 있는 것으로 본다(보수적)."""
    keys = [k for k in ("rows", "points", "series") if k in obj]
    if not keys:
        return True
    for k in keys:
        v = obj[k]
        if k == "series" and isinstance(v, list):
            if any(isinstance(s, dict) and s.get("points") for s in v):
                return True
        elif v:
            return True
    return False


def mark_binding_stale(payload: Any, path: str, targets: list[tuple[str, str]], reason: str | None) -> bool:
    """바인딩이 채우는 표 · 차트 · 계열에 '갱신 실패' 표시(`stale` · `staleReason`)를 달거나(reason) 뗀다(reason=None).
    계산이 실패해도 이전 값은 두되, 화면에는 갱신 실패로 보이고 검색 · 질문하기 색인에는 값이 실리지 않는다 (DEL-11). 바뀌었으면 True."""
    if not path.startswith(STALE_MARK_PREFIXES):
        return False
    changed = False
    why = (reason or "")[:200]
    for parent, _fld in targets:
        try:
            obj = get_parent(payload, parent)
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        if reason is not None and not _has_content(obj):
            continue  # 비어 있는 표 · 차트에는 '이전 값'이 없다 — 갱신 실패 표시를 달지 않는다 (빈 상태에서 실행마다 새 세대가 생기지 않게)
        if reason is None:
            for k in ("stale", "staleReason"):
                if k in obj:
                    del obj[k]
                    changed = True
        elif obj.get("stale") is not True or obj.get("staleReason") != why:
            obj["stale"], obj["staleReason"] = True, why
            changed = True
    return changed


# ═════════════════════════ 화면 틀 ═════════════════════════
def strip_figure(d: dict[str, Any]) -> None:
    d["value"] = None
    for k in FIG_DROP:
        d.pop(k, None)


def to_template(key: str, payload: Any, bindings: Iterable[dict[str, Any]] = ()) -> Any:
    """화면 산출물 → 값 없는 틀. 수치 값 · 계산 근거 · 데이터 성격 제거, 바인딩 대상 목록 비움, 시연 전용 목록 비움, 서식 문구는 '–' 로."""
    if key in DEMO_ARTIFACTS:
        return copy.deepcopy(DEMO_ARTIFACTS[key])
    p = copy.deepcopy(payload)

    def fix(d: dict[str, Any]) -> None:
        if is_figure(d):
            strip_figure(d)
        if "relevance" in d and isinstance(d.get("relevance"), (int, float)) and ("doc" in d or "snippet" in d):
            d["relevance"] = None  # 근거 관련도는 검색 시점 점수 — 틀에 두지 않는다
        if "statement" in d:
            for k in ("asOf", "rankScore", "rankBasis", "rankCalcId", "rankRule", "rankReason", "rankReasonBy"):
                if k in d:
                    d[k] = None
        for k in [k for k in d if k.endswith("Metric") and len(k) > 6 and isinstance(d[k], str)]:
            d[k[:-6]] = None  # 지표 표시값으로 채우는 숫자 필드
        if "gapVerdict" in d:
            d["gapVerdict"] = None  # 목표 판정은 실적 수치로 서버가 계산한다 (views.goal_verdict) — 틀에는 두지 않는다
        # 실행 때 생기는 것 — 문서 인용 근거(attach_evidence) · 검증 결과(critic) · 근거 문서(basisDoc) · 배치 확인 문서 · 에이전트 문장 표시
        if isinstance(d.get("evidence"), list):
            d["evidence"] = [e for e in d["evidence"] if not (isinstance(e, dict) and any(k in e for k in DOC_EVIDENCE_KEYS))]
        if isinstance(d.get("verifications"), list):
            d["verifications"] = []
        if "basisDoc" in d:
            d["basisDoc"] = None
        if isinstance(d.get("alignment"), dict) and isinstance(d["alignment"].get("matched"), list):
            d["alignment"]["matched"] = []
        for k in [k for k in d if k.endswith(BY) and len(k) > len(BY) and k[: -len(BY)] in d and d[k] == "llm"]:
            del d[k]
        if d.get("mode") in ("range", "point") and "unit" in d and any(k in d for k in ("low", "high", "value")):
            # 경영목표 추천값(제안의 recommendation) — 계산 커널이 채운다(recommend_goals). 자료가 없을 때 시드의 고정 숫자가 '추천'처럼 보이지 않게
            for k in ("low", "high", "value", "currentValue"):
                if k in d:
                    d[k] = None
            d["text"] = ""
            d.pop("calcId", None)
            d.pop("engine", None)

    _walk(p, fix)
    if isinstance(p, dict):
        for k in ("asOf", "generatedAt"):
            if k in p:
                p[k] = None
        for fld in DEMO_FIELDS.get(key, []):
            if isinstance(p.get(fld), list):
                p[fld] = []
    for b in bindings:
        if b.get("artifact_key") != key:
            continue
        for parent, fld in binding_targets(p, b["path"]):
            try:
                obj = get_parent(p, parent)
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            cur = obj.get(fld) if isinstance(obj, dict) else None
            obj[fld] = "" if fld == "note" else ([] if isinstance(cur, list) or cur is None else ({} if isinstance(cur, dict) else None))
    render_templates(p, {}, None, protect=False)
    return p


# ═════════════════════════ 서식 문구 렌더 ═════════════════════════
def figure_index(artifacts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """id → Figure (값이 있는 것을 우선)."""
    idx: dict[str, dict[str, Any]] = {}

    def add(d: dict[str, Any]) -> None:
        if is_figure(d):
            cur = idx.get(d["id"])
            if cur is None or (cur.get("value") is None and d.get("value") is not None):
                idx[d["id"]] = d

    for payload in artifacts.values():
        _walk(payload, add)
    return idx


def _num(v: float, d: int) -> str:
    from nhdip.reports.model import number

    return number(v, d)


def fmt_figure(f: dict[str, Any] | None, mode: str | None, units: dict[str, str]) -> str:
    if f is None:
        return DASH
    if mode == "verdict":
        return f.get("verdict") or DASH
    if mode == "severity":
        return f.get("severity") or ""
    unit = f.get("unit") or "NONE"
    if mode == "unit":
        return units.get(unit, "")
    v = f.get("value")
    if v is None or isinstance(v, bool):
        return DASH
    from nhdip.reports.model import DEFAULT_DECIMALS

    d = f.get("decimals")
    d = DEFAULT_DECIMALS.get(unit, 0) if d is None else int(d)
    s = _num(abs(v) if mode == "abs" else v, d)
    if mode == "signed" and v > 0:
        s = "+" + s
    return s if mode == "num" else s + units.get(unit, "")


def fmt_period(value: Any, mode: str | None) -> str:
    s = re.sub(r"[^0-9]", "", str(value or ""))
    if len(s) < 6:
        return DASH
    y, m, d = s[:4], s[4:6], s[6:8]
    mode = mode or "dot"
    if mode == "ym":
        return y + m
    if mode == "year":
        return y
    if mode == "month":
        return f"{int(m)}월"
    if mode == "kor":
        return f"{y}년 {int(m)}월"
    if mode == "date":
        if not d:
            import calendar

            d = f"{calendar.monthrange(int(y), int(m))[1]:02d}"
        return f"{y}.{m}.{d}"
    return f"{y}.{m}"


def _period(ctx: Any, arg: str, mode: str | None) -> str:
    if ctx is None:
        return DASH
    from nhdip.calc.metrics import ResolveError, resolve_token

    code, _, token = arg.partition(":")
    try:
        _, rows, ds = ctx.dataset(code.strip())
        col = ds.as_of_column
        if not col:
            return DASH
        return fmt_period(resolve_token(rows, col, (token or "$latest").strip()), mode)
    except (ResolveError, ValueError, KeyError):
        return DASH


def _rule(ctx: Any, arg: str, mode: str | None) -> str:
    if ctx is None:
        return DASH
    from nhdip.calc.metrics import TOKEN_RE, ResolveError, anchor_dataset, resolve_period, resolve_ref

    code, _, path = arg.partition(".")
    ref = {"rule": code.strip(), "path": path.strip()}
    try:
        v = resolve_ref(ctx, ref)[0]
    except (ResolveError, ValueError, KeyError):
        return DASH
    if mode in ("dot", "month", "year", "ym", "date", "kor"):
        # 규칙 값이 기간 토큰($prev · $earliest · $latest …)이면 실제 기준일로 푼다 — 라벨이 고정 연월이 아니라
        # 이번에 견준 기간을 보여 주게. 어느 자료의 보관 기간에서 고를지는 규칙 본문의 '<키>_source'(자료 이름)
        if isinstance(v, str) and TOKEN_RE.match(v):
            try:
                anchor = anchor_dataset(ctx, ref)
                if not anchor:
                    return DASH  # 기준 자료가 없으면 어느 기간인지 말할 수 없다 — 토큰을 글자로 찍지 않는다
                v = resolve_period(ctx, v, anchor=anchor, rows=[], col="")
            except (ResolveError, ValueError, KeyError, TypeError):
                return DASH
        return fmt_period(v, mode)  # 기준월 같은 기간 규칙 값
    if mode == "pct0" and isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{_num(v * 100, 0)}%"  # 0.95 → 95%
    m = re.fullmatch(r"(\+?)d(\d)", mode or "")
    if m and isinstance(v, (int, float)) and not isinstance(v, bool):
        s = _num(v, int(m.group(2)))
        return ("+" + s) if m.group(1) and v > 0 else s
    if isinstance(v, str) and TOKEN_RE.match(v):
        return DASH  # 기간 토큰은 기간 형식(dot · month …)으로만 쓴다 — '$prev' 가 화면에 글자로 나가지 않게
    return DASH if v is None else str(v)


def _operand(tok: str, idx: dict[str, dict[str, Any]]) -> float | None:
    try:
        return float(tok)
    except ValueError:
        pass
    f = idx.get(tok)
    v = f.get("value") if isinstance(f, dict) else None
    return None if v is None or isinstance(v, bool) else float(v)


def eval_condition(expr: str, idx: dict[str, dict[str, Any]]) -> bool | None:
    """'A>B' — 수치 id 또는 숫자 비교. 값이 없거나 식이 틀리면 None."""
    m = IF_EXPR.match(expr)
    if not m:
        return None
    a, op, b = _operand(m.group(1), idx), m.group(2), _operand(m.group(3), idx)
    if a is None or b is None:
        return None
    return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b, "=": a == b, "!=": a != b}[op]


def _at(root: Any, path: str) -> str:
    obj = root
    for p in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(p)
        elif isinstance(obj, list) and p.isdigit() and int(p) < len(obj):
            obj = obj[int(p)]
        else:
            return DASH
    return DASH if obj in (None, "") or isinstance(obj, (dict, list)) else str(obj)


def render_text(tpl: str, idx: dict[str, dict[str, Any]], ctx: Any = None, units: dict[str, str] | None = None, *, keep_fig: bool = False, root: Any = None) -> str:
    units = units or UNIT_LABELS

    def pick(m: re.Match) -> str:
        ok = eval_condition(m.group(1), idx)
        return (m.group(4) or "") if ok is None else (m.group(2) if ok else m.group(3))

    def rep(m: re.Match) -> str:
        kind, arg, mode = m.group(1), m.group(2), m.group(3)
        if kind == "fig":
            # 화면은 꾸밈 없는 [[fig:ID]] 만 수치 칩으로 그린다 — 꾸밈(signed · verdict …)이 붙은 표식은 서버가 글로 렌더한다
            return m.group(0) if keep_fig and not mode else fmt_figure(idx.get(arg.strip()), mode, units)
        if kind == "ym":
            return _period(ctx, arg, mode)
        return _rule(ctx, arg, mode)

    out = IF_TOKEN.sub(pick, tpl)
    out = AT_TOKEN.sub(lambda m: _at(root, m.group(1)), out)
    return TOKEN.sub(rep, out)


def template_figure_ids(d: dict[str, Any]) -> set[str]:
    """이 객체가 기대는 수치 id — 품은 Figure · figures 사전 · 서식 문구의 [[fig:ID]] · [[if:..]] 피연산자."""
    out: set[str] = set()

    def add(o: dict[str, Any]) -> None:
        if is_figure(o):
            out.add(o["id"])
        for k, v in o.items():
            if k.endswith(TPL) and isinstance(v, (str, list)):
                for s in ([v] if isinstance(v, str) else [x for x in v if isinstance(x, str)]):
                    out.update(x.strip() for x in re.findall(r"\[\[fig:([^\]|]+)", s))
                    for e in re.findall(r"\[\[if:([^\]|]+)\|", s):
                        m = IF_EXPR.match(e)
                        if m:
                            out.update(t for t in (m.group(1), m.group(3)) if not re.fullmatch(r"-?[0-9.]+", t))

    _walk(d, add)
    return out


def render_templates(payload: Any, idx: dict[str, dict[str, Any]], ctx: Any = None, units: dict[str, str] | None = None, *,
                     protect: bool = True, refresh: set[str] | None = None) -> bool:
    """`xxxTpl`(문자열 · 문자열 목록) → `xxx`. 바뀐 것이 있으면 True.

    protect — 에이전트가 쓴 필드(`xxxBy: "llm"`)는 건너뛴다. 단 그 객체 id 가 `refresh`(이번 실행에 기대는 수치가 바뀐 객체)에 있으면
    표시를 떼고 규칙 문장으로 되돌린다(바뀐 수치에 맞지 않을 수 있는 옛 서술을 남기지 않게 — 이어지는 서술 단계가 다시 쓴다)."""
    changed = False

    def fix(d: dict[str, Any]) -> None:
        nonlocal changed
        for k in [k for k in d if k.endswith(TPL) and len(k) > len(TPL)]:
            tpl, fld = d[k], k[: -len(TPL)]
            if d.get(fld + BY) == "llm":
                if protect and not (refresh and d.get("id") in refresh):
                    continue
                del d[fld + BY]
                changed = True
            keep = fld in KEEP_FIG_FIELDS
            if isinstance(tpl, str):
                new: Any = render_text(tpl, idx, ctx, units, keep_fig=keep, root=payload)
            elif isinstance(tpl, list) and all(isinstance(x, str) for x in tpl):
                new = [render_text(x, idx, ctx, units, keep_fig=keep, root=payload) for x in tpl]
            else:
                continue
            if d.get(fld) != new:
                d[fld] = new
                changed = True

    _walk(payload, fix)
    return changed


def apply_metric_fields(payload: Any, outcomes: dict[str, Any]) -> bool:
    """`xxxMetric`(지표 코드) → `xxx` = 이번 실행의 지표 표시값(숫자 필드 — 진행률 막대 등). 이번 실행에 없는 지표는 두지 않는다."""
    changed = False

    def fix(d: dict[str, Any]) -> None:
        nonlocal changed
        for k in [k for k in d if k.endswith("Metric") and len(k) > 6 and isinstance(d[k], str)]:
            oc = outcomes.get(d[k])
            if oc is None:
                continue
            fld = k[:-6]
            new = None if oc.error or oc.display is None else float(oc.display)
            if d.get(fld) != new:
                d[fld] = new
                changed = True

    _walk(payload, fix)
    return changed


def strip_tpl(payload: Any) -> Any:
    """응답 · 색인용 사본에서 서식 원문(`xxxTpl` · `bindKey`)을 뺀다."""
    if isinstance(payload, dict):
        return {k: strip_tpl(v) for k, v in payload.items() if not (k.endswith(TPL) and len(k) > len(TPL)) and k != "bindKey"}
    if isinstance(payload, list):
        return [strip_tpl(v) for v in payload]
    return payload
