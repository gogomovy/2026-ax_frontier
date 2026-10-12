"""산출물 선형화 · 청크 분할 (요구사항 KB-02 · KB-10 · 설계 §21.5).

화면 산출물(JSON)을 '제목이 붙은 글 블록'으로 펼친 뒤 검색 단위(청크)로 나눈다. 산출물이 30여 종이고 분석 에이전트 보고서가
계속 늘어도 코드를 고치지 않도록 산출물별 파서를 두지 않고 구조 규칙(제목 · 서술 · 수치 · 시계열 · 표 · 블록)으로 읽는다.

원칙
- 수치는 계산 커널이 확정한 값 · 단위를 풀어 쓴 문장으로 — `[[fig:ID]]` 마커는 산출물 안의 수치 사전으로 풀고, 풀 수 없으면
  값을 지어내지 않고 '수치 미확인' 으로 둔다.
- 같은 입력이면 같은 청크(결정적) — 청크 본문 해시가 행 식별자다(멱등 · 임베딩 재사용).
- 접근 경계(페르소나 · 화면 리소스 · 담당 부서)가 다른 블록은 한 청크로 합치지 않는다.
- 개인정보 형식 값은 가린다.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from nhdip.privacy import mask_text

UNIT_LABELS = {"PCT": "%", "PP": "%p", "KRW_TN": "조원", "KRW_BN": "억원", "KRW_MN": "백만원", "CNT": "건", "RATIO": "", "NONE": ""}
SEV_ORDER = {"info": 0, "watch": 1, "caution": 2, "critical": 3}
SEV_KO = {"info": "정보", "watch": "관찰", "caution": "주의", "critical": "심각"}
STATUS_KO = {"open": "진행 중(열림)", "proposed": "제안", "ai_proposed": "AI 제안", "in_progress": "진행 중", "active": "유효", "done": "완료", "closed": "종료", "draft": "초안", "pending": "대기", "reviewing": "검토 중"}
VERDICT_KO = {
    "below": "목표 미달", "breach": "관리목표 초과", "on_track": "목표 순항", "near_limit": "한도 근접", "aligned": "정책 정합", "conflict": "정책 상충",
    "within_mid": "대표값 이내", "above_mid_within_max": "대표값 초과 · 최대값 이내", "above_max": "최대값 초과",
}
DIRECTION_KO = {"increase": "확대(증가)", "decrease": "축소(감소) 관리", "maintain": "유지"}
TARGET_TYPE_KO = {"amount": "금액", "growth": "증가율", "limit": "한도", "ratio": "비율"}
VALUE_KO = {"severity": SEV_KO, "status": STATUS_KO, "verdict": VERDICT_KO, "gapVerdict": VERDICT_KO, "direction": DIRECTION_KO, "targetType": TARGET_TYPE_KO}
CITE_KEYS = ("src", "doc", "basisDoc")  # 출처 인용 객체 — 문서 제목 · 발행처 · 쪽을 한 줄로

# 의미 있는 짧은 필드 → 한글 이름 (그 밖의 짧은 문자열 · 코드는 본문에 넣지 않는다)
LABELS = {
    "severity": "심각도", "status": "상태", "verdict": "판정", "gapVerdict": "판정", "ownerOrg": "담당 부서", "fromOrg": "요청 부서", "toOrg": "수신 부서", "orgName": "조직",
    "dueDate": "기한", "periodLabel": "기간", "asOfLabel": "기준", "reviewCycle": "점검 주기", "relatedGoalTitle": "관련 목표", "sourcePlanTitle": "원천 수행방안",
    "sourceGoalTitle": "원천 경영목표", "metricLabel": "지표", "reqTypeLabel": "요청 유형", "altLabels": "다른 이름", "relatedTerms": "관련 용어", "direction": "방향",
    "targetType": "목표 유형", "path": "경로", "changeType": "변경", "changeSummary": "변경 내용", "itemCode": "항목 코드",
    "reportCode": "리포트 코드", "asOfYm": "기준년월", "quality": "품질 검증", "qualityNote": "품질 메모", "usedBy": "사용처",
}
NUM_LABELS = {"score": "득점", "max": "배점", "progress": "진행률(%)", "rank": "순위", "rows": "행 수"}
SKIP_DEFAULT = {
    "id", "kind", "calc", "sourceRef", "tableRef", "dataOrigin", "executedAt", "formulaId", "formulaVersion", "href", "verifications", "rankScore", "rankBasis",
    "generatedAt", "degradedSources", "batchLabel", "persona", "domainCode", "subDomain", "sourceKind", "figureId", "checkCode", "reportAnchor", "tabKey", "reportKind",
    "insightId", "relatedGoalId", "sourceInsightId", "linkedTabKey", "guideRuleId", "creationMode", "history", "toc", "unit", "decimals", "generation", "office",
}
TITLE_KEYS = ("title", "name", "heading", "caption", "label", "assetClass", "org", "prefLabel")
DEFAULT_TITLES = {
    "hq_dashboard": "종합기획부 대시보드", "attentions": "AI Attention 우선순위", "loan_overview": "여신 현황 분석", "comparison_view": "기업 · 가계여신 비교",
    "capital_view": "총자산 · 자본(RWA) 제약", "profitability": "수익성 트래킹", "goals": "경영목표", "proposals": "경영목표 수정 · 신설 제안", "review_queue": "목표 검토 대기",
    "cascade": "경영목표 전파 경로", "report_requests": "확인 · 보고 요청", "risk_dashboard": "신용리스크 대시보드", "analysis_tabs": "신용리스크 분석 탭",
    "inclusive": "포용금융 충당금 비중 분석", "default_rate_trend": "월별 부도율 추이", "insights": "신용리스크 인사이트", "action_plans": "수행방안(진행사업)",
    "branch_dashboard": "영업점 업적평가 현황", "branch_tabs": "영업점 분석 탭", "branch_targets": "본부 전파 목표 · 가이드", "terms": "용어집", "dataset_meta": "데이터 목록(적재 현황)",
}

FIG_MARK = re.compile(r"\[\[fig:([^\]]+)\]\]")
TERM_MARK = re.compile(r"\{\{term:([^|}]+)\|?([^}]*)\}\}")
ID_LIKE = re.compile(r"^[A-Za-z0-9_.:@/#\-]+$")
DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$")
SENT_SPLIT = re.compile(r"(?<=[.!?。다요함음임])\s+")
MAX_DEPTH = 14
SUB_HEADS = ("근거", "관련 수치")  # 제목 경로의 보조 머리 — 청크 제목에서는 뺀다


@dataclass
class Block:
    path: tuple[str, ...]
    lines: list[str]
    persona: str | None = None
    resource: str | None = None
    owner: str | None = None  # 조직 이름 (indexer 가 코드로 바꾼다)
    severity: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class ChunkDraft:
    ordinal: int
    title: str
    section_path: str | None
    text: str
    unit_hash: str
    persona: str | None = None
    resource: str | None = None
    owner: str | None = None
    severity: str | None = None


@dataclass
class Rendered:
    title: str
    as_of: date | None
    office: dict[str, Any] | None
    drafts: list[ChunkDraft] = field(default_factory=list)


# ── 수치 표기 ─────────────────────────────────────────────────
def fmt_num(v: Any, decimals: Any = None) -> str:
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if not isinstance(v, (int, float)):
        return str(v)
    if isinstance(decimals, int) and decimals >= 0:
        return f"{v:,.{decimals}f}"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.6f}".rstrip("0").rstrip(".")
    return f"{int(v):,}"


def is_figure(d: Any) -> bool:
    return isinstance(d, dict) and "id" in d and "label" in d and "unit" in d and "value" in d


def fig_text(f: dict[str, Any]) -> str:
    """수치 하나를 `값단위` 로 — 소수 자릿수 · 단위 문자 적용. 값이 없으면 '미산출' (없는 값을 지어내지 않는다)."""
    if f.get("value") is None:
        return "미산출"
    unit = UNIT_LABELS.get(str(f.get("unit")), "" if f.get("unit") in (None, "") else str(f.get("unit")))
    return f"{fmt_num(f.get('value'), f.get('decimals'))}{unit}"


def fig_line(f: dict[str, Any]) -> str:
    return f"{f.get('label') or f.get('id')}: {fig_text(f)}"


def collect_figures(node: Any, out: dict[str, dict[str, Any]] | None = None, depth: int = 0) -> dict[str, dict[str, Any]]:
    """산출물 전체의 수치 사전 {id: 수치} — `[[fig:ID]]` 를 풀 때 쓴다. 같은 id 가 여러 번이면 처음 것."""
    out = {} if out is None else out
    if depth > MAX_DEPTH:
        return out
    if isinstance(node, dict):
        if is_figure(node):
            out.setdefault(str(node["id"]), node)
        for v in node.values():
            collect_figures(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            collect_figures(v, out, depth + 1)
    return out


def resolve_text(s: str, figs: dict[str, dict[str, Any]]) -> str:
    """`[[fig:ID]]` → 확정값 문장, `{{term:코드|표시}}` → 표시 글자. 풀 수 없는 마커는 '수치 미확인'."""
    s = FIG_MARK.sub(lambda m: fig_text(figs[m.group(1)]) if m.group(1) in figs else "(수치 미확인)", s)
    return TERM_MARK.sub(lambda m: (m.group(2) or m.group(1)), s)


def is_series(v: Any) -> bool:
    return (
        isinstance(v, list) and len(v) >= 2
        and all(isinstance(i, dict) and "label" in i and isinstance(i.get("value"), (int, float)) and not isinstance(i.get("value"), bool) and len(i) <= 3 for i in v)
    )


def series_text(pts: list[dict[str, Any]]) -> str:
    if len(pts) <= 4:
        return ", ".join(f"{p['label']} {fmt_num(p['value'])}" for p in pts)
    lo = min(pts, key=lambda p: p["value"])
    hi = max(pts, key=lambda p: p["value"])
    return f"{pts[0]['label']} {fmt_num(pts[0]['value'])} → {pts[-1]['label']} {fmt_num(pts[-1]['value'])} (최소 {lo['label']} {fmt_num(lo['value'])}, 최대 {hi['label']} {fmt_num(hi['value'])})"


# ── 선형화 ───────────────────────────────────────────────────
class _Renderer:
    def __init__(self, key: str, payload: Any, cfg: dict[str, Any]):
        self.key = key
        self.payload = payload
        self.cfg = cfg
        self.skip = set(cfg.get("skip_keys") or SKIP_DEFAULT)
        self.table_rows = int(cfg.get("table_rows", 12))
        self.figs = collect_figures(payload)
        self.blocks: list[Block] = []
        base = key.split("@", 1)[0]
        titles = {**DEFAULT_TITLES, **(cfg.get("titles") or {})}
        title = payload.get("title") if isinstance(payload, dict) and isinstance(payload.get("title"), str) else None
        self.office = payload.get("office") if isinstance(payload, dict) and isinstance(payload.get("office"), dict) else None
        self.title = (title or titles.get(base) or base).strip()
        if self.office and self.office.get("name"):
            self.title = f"{self.title} — {self.office['name']}"
        self.title = mask_text(self.title)

    # 블록 추가
    def emit(self, path: tuple[str, ...], lines: list[str], meta: dict[str, Any]) -> None:
        lines = [mask_text(ln) for ln in lines if ln and ln.strip()]
        if lines:
            self.blocks.append(Block(path=path, lines=lines, persona=meta.get("persona"), resource=meta.get("resource"), owner=meta.get("owner"), severity=meta.get("severity")))

    def text(self, s: str) -> str:
        return resolve_text(s, self.figs).strip()

    def scalar_line(self, k: str, v: Any, node: dict[str, Any]) -> str | None:
        if isinstance(v, str):
            s = self.text(v)
            if not s:
                return None
            if k in LABELS:
                s = VALUE_KO.get(k, {}).get(s, s)
                return f"{LABELS[k]}: {s}"
            if len(s) >= 8 and not ID_LIKE.match(s) and not DATE_LIKE.match(s):
                return s
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if k in NUM_LABELS:
                return f"{NUM_LABELS[k]}: {fmt_num(v)}"
            if k == "targetValue":
                unit = UNIT_LABELS.get(str(node.get("unit")), "")
                return f"목표값: {fmt_num(v, node.get('decimals'))}{unit}"
        return None

    def walk(self, node: Any, path: tuple[str, ...], meta: dict[str, Any], depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            return
        if isinstance(node, list):
            if is_series(node):
                self.emit(path, [f"추이: {series_text(node)}"], meta)
                return
            for it in node:
                self.walk(it, path, meta, depth + 1)
            return
        if not isinstance(node, dict):
            return
        if is_figure(node):
            self.emit(path, [fig_line(node)], meta)
            return
        meta = dict(meta)
        if isinstance(node.get("persona"), str):
            meta["persona"] = node["persona"]
        if isinstance(node.get("ownerOrg"), str):
            meta["owner"] = node["ownerOrg"]
        if isinstance(node.get("severity"), str) and SEV_ORDER.get(node["severity"], -1) > SEV_ORDER.get(meta.get("severity") or "", -1):
            meta["severity"] = node["severity"]
        # 영업점 참고가 켜진 진행 중 수행방안은 영업점도 화면에서 본다 (screens.action_plans 와 같은 기준 — ACL-05)
        if self.key.split("@", 1)[0] == "action_plans" and "branchShared" in node:
            meta["resource"] = "action_plans" if node.get("branchShared") and node.get("status") == "in_progress" else None
        title = next((self.text(node[k]) for k in TITLE_KEYS if isinstance(node.get(k), str) and node[k].strip()), None)
        title = mask_text(title) if title else title  # 제목 · 경로도 본문과 같이 개인정보 형식 값을 가린다(KB-10)
        here = path + (title[:80],) if title else path
        used_title = next((k for k in TITLE_KEYS if isinstance(node.get(k), str) and node[k].strip()), None)
        lines: list[str] = []
        for k, v in node.items():
            if k in self.skip or k == used_title:
                continue
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                ln = self.scalar_line(k, v, node)
                if ln:
                    lines.append(ln)
            elif k in CITE_KEYS and isinstance(v, dict):
                cite = self.citation(v)
                if cite:
                    lines.append(cite)
            elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                strs = [self.text(x) for x in v if x and x.strip()]
                if k in LABELS:
                    lines.append(f"{LABELS[k]}: {', '.join(strs)}")
                elif k == "limitations":
                    lines += [f"한계: {x}" for x in strs]
                else:
                    lines += [f"- {x}" for x in strs if len(x) >= 8]
        if lines:
            self.emit(here, lines, meta)
        for k, v in node.items():
            if k in self.skip or k in CITE_KEYS:
                continue
            if k == "blocks" and isinstance(v, list):
                self.blocks_of(v, here, meta)
            elif k == "evidence" and isinstance(v, list):
                self.evidence(v, here, meta)
            elif k in ("figures", "narrativeFigures") and isinstance(v, dict):
                figs = [fig_line(f) for f in v.values() if is_figure(f)]
                if figs:
                    self.emit(here + ("관련 수치",), figs, meta)
            elif k == "points" and is_series(v):
                self.emit(here, [f"추이: {series_text(v)}"], meta)
            elif isinstance(v, (dict, list)):
                if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                    continue
                self.walk(v, here, meta, depth + 1)

    def citation(self, d: dict[str, Any]) -> str | None:
        title = d.get("title") or d.get("fileName")
        if not isinstance(title, str) or not title.strip():
            return None
        bits = [self.text(title)]
        if d.get("issuer"):
            bits.append(str(d["issuer"]))
        if d.get("page"):
            bits.append(f"p.{d['page']}")
        return "출처: " + " · ".join(bits)

    def evidence(self, items: list[Any], path: tuple[str, ...], meta: dict[str, Any]) -> None:
        lines = []
        for e in items:
            if not isinstance(e, dict):
                continue
            label = self.text(e.get("label") or "")
            snippet = self.text(e.get("snippet") or "")
            doc = e.get("doc") if isinstance(e.get("doc"), dict) else None
            where = f" ({doc.get('title')}{' p.' + str(doc['page']) if doc.get('page') else ''})" if doc and doc.get("title") else ""
            if label or snippet:
                lines.append(f"근거: {label}{' — ' + snippet if snippet else ''}{where}")
        self.emit(path + ("근거",), lines, meta)

    def blocks_of(self, blocks: list[Any], path: tuple[str, ...], meta: dict[str, Any]) -> None:
        for b in blocks:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            lines: list[str] = []
            if t in ("p", "callout") and isinstance(b.get("text"), str):
                lines.append(self.text(b["text"]))
            elif t == "ul":
                lines += [f"- {self.text(x)}" for x in b.get("items") or [] if isinstance(x, str)]
            elif t == "kv":
                lines += [f"- {self.text(str(i.get('label', '')))}: {self.text(str(i.get('value', '')))}" for i in b.get("kv") or [] if isinstance(i, dict)]
            elif t == "table" and isinstance(b.get("table"), dict):
                lines += self.table(b["table"])
            elif t == "chart" and isinstance(b.get("chart"), dict):
                ch = b["chart"]
                if ch.get("title"):
                    lines.append(f"그래프: {self.text(str(ch['title']))}")
                for s in ch.get("series") or []:
                    if isinstance(s, dict) and is_series(s.get("points")):
                        lines.append(f"- {s.get('name', '계열')}: {series_text(s['points'])}")
            self.emit(path, lines, meta)

    def table(self, tb: dict[str, Any]) -> list[str]:
        cols = [c for c in tb.get("columns") or [] if isinstance(c, dict) and c.get("key")]
        out = [f"표: {self.text(str(tb.get('caption', '')))}"] if tb.get("caption") else []
        for row in (tb.get("rows") or [])[: self.table_rows]:
            if isinstance(row, dict):
                out.append("- " + "; ".join(f"{c.get('label') or c['key']}={self.text(str(row.get(c['key'], '')))}" for c in cols if row.get(c["key"]) not in (None, "")))
        if len(tb.get("rows") or []) > self.table_rows:
            out.append(f"- (외 {len(tb['rows']) - self.table_rows}행)")
        if tb.get("note"):
            out.append(self.text(str(tb["note"])))
        return out

    def run(self) -> None:
        self.walk(self.payload, (self.title,), {})


# ── 청크 분할 ────────────────────────────────────────────────
def _split_long(line: str, size: int, overlap: int) -> list[str]:
    if len(line) <= size:
        return [line]
    parts: list[str] = []
    buf = ""
    for sent in SENT_SPLIT.split(line):
        if len(buf) + len(sent) + 1 <= size:
            buf = f"{buf} {sent}".strip()
            continue
        if buf:
            parts.append(buf)
        while len(sent) > size:
            parts.append(sent[:size])
            sent = sent[size - overlap :]
        buf = sent
    if buf:
        parts.append(buf)
    return parts


def chunk_blocks(blocks: list[Block], cfg: dict[str, Any], root_title: str) -> list[ChunkDraft]:
    """블록을 순서대로 모아 청크로 — 접근 경계(페르소나 · 리소스 · 담당 부서)가 바뀌거나 길이를 넘으면 끊고,
    짧은 청크는 같은 경계 안의 다음 블록과 합친다(소제목 줄 `[경로]` 로 구분)."""
    size = int(cfg.get("chunk_chars", 900))
    overlap = int(cfg.get("overlap", 80))
    min_chars = max(120, size // 4)
    drafts: list[ChunkDraft] = []
    cur: list[str] = []
    cur_blocks: list[Block] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_blocks, cur_len
        if not cur_blocks:
            return
        first = cur_blocks[0]
        head = " > ".join(first.path)
        body = "\n".join(cur)
        text = f"{head}\n{body}" if head else body
        sev = max((b.severity for b in cur_blocks if b.severity), key=lambda s: SEV_ORDER.get(s, 0), default=None)
        names = [p for p in first.path if p not in SUB_HEADS]
        # 식별자에 접근 경계(페르소나 · 리소스 · 담당 부서)를 넣는다 — 본문이 같아도 열람 범위가 다른 청크를 하나로 합쳐 권한이 섞이지 않게
        ident = f"{first.persona}|{first.resource}|{first.owner}\n{text}"
        drafts.append(ChunkDraft(
            ordinal=len(drafts), title=(names[-1] if names else root_title)[:300], section_path=(head[:500] or None), text=text,
            unit_hash=hashlib.sha1(ident.encode("utf-8")).hexdigest()[:40], persona=first.persona, resource=first.resource, owner=first.owner, severity=sev,
        ))
        cur, cur_blocks, cur_len = [], [], 0

    for b in blocks:
        for piece in _split_long("\n".join(b.lines), size, overlap):
            boundary = bool(cur_blocks) and (b.persona, b.resource, b.owner) != (cur_blocks[0].persona, cur_blocks[0].resource, cur_blocks[0].owner)
            same_path = bool(cur_blocks) and b.path == cur_blocks[-1].path
            if cur_blocks and (boundary or cur_len + len(piece) > size or (not same_path and cur_len >= min_chars)):
                flush()
            if cur_blocks and not same_path:
                cur.append(f"[{' > '.join(b.path[len(cur_blocks[0].path):] or b.path[-1:])}]")
            cur.append(piece)
            cur_blocks.append(Block(path=b.path, lines=[piece], persona=b.persona, resource=b.resource, owner=b.owner, severity=b.severity))
            cur_len += len(piece)
    flush()
    # 같은 본문(해시)은 한 번만 — 산출물 안에서 같은 서술이 여러 곳에 있어도 행이 겹치지 않게
    seen: set[str] = set()
    out: list[ChunkDraft] = []
    for d in drafts:
        if d.unit_hash in seen:
            continue
        seen.add(d.unit_hash)
        d.ordinal = len(out)
        out.append(d)
    return out


def _as_of(payload: Any) -> date | None:
    v = payload.get("asOf") if isinstance(payload, dict) else None
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def render_artifact(key: str, payload: Any, cfg: dict[str, Any] | None = None) -> Rendered:
    """산출물 하나 → 청크 초안 목록 (결정적 — 같은 입력이면 같은 해시)."""
    cfg = cfg or {}
    r = _Renderer(key, payload, cfg)
    r.run()
    return Rendered(title=r.title, as_of=_as_of(payload), office=r.office, drafts=chunk_blocks(r.blocks, cfg, r.title))
