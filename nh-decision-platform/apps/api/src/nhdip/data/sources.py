"""자료 이름 → 지금 있는 데이터셋 (Phase O · BIZ-03 · Q216 · Q217).

업무 구성(지표 · 화면 연결 · 흐름 조건 · 표식)은 데이터셋 코드가 아니라 업무 구성 파일 '자료' 시트의 이름으로 원천을 가리킨다.
데이터셋 코드는 올린 파일 이름 · 순서로 정해지므로(파일에서 만든 정의) 구성에 코드를 적으면 다시 하드코딩이 된다.

  자료 정의    {name, columns: [필요한 열 이름], keywords: [이름 단서], aliases: {코드용 이름: 파일의 열 이름}}
  찾기         ① 그 이름이 데이터셋 코드면 그것 ② 활성 구성의 자료 정의 — 필요한 열이 모두 있는 데이터셋 중 이름 단서가 많이 맞는 것 →
               확정 버전이 있는 것 → 최근 확정 순 ③ 정의가 없으면 데이터셋 이름이 같은 것
  못 찾음       '자료 대기' — 그 자료가 올라오면(정의가 생기면) 다음 계산 · 이벤트부터 바로 이어진다(코드를 저장하지 않으므로)
  별칭         표 · 행 생성기(코드)가 읽는 값 이름을 파일의 열에 잇는다 — 읽은 행에 별칭 열을 더할 뿐 자료는 바뀌지 않는다
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.models import BusinessConfig, Dataset, source


def norm(s: Any) -> str:
    return re.sub(r"[\s_\-()·./\[\]]+", "", str(s or "")).lower()


@dataclass
class SourceSpec:
    name: str
    columns: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    description: str = ""
    config_id: int | None = None
    config_name: str = ""
    mapping: dict[str, Any] = field(default_factory=dict)  # 온톨로지 연결(nodes · edges · concepts) — 이어진 데이터셋의 정의 mapping 처럼 그래프에 쓴다


def spec_from(d: dict[str, Any], config_id: int | None = None, config_name: str = "") -> SourceSpec:
    def _list(v: Any) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in re.split(r"[,\n]", v) if x.strip()]
        return [str(x).strip() for x in (v or []) if str(x).strip()]

    al = d.get("aliases") or {}
    return SourceSpec(name=str(d.get("name") or "").strip(), columns=_list(d.get("columns")), keywords=_list(d.get("keywords")),
                      aliases={str(k): str(v) for k, v in al.items()} if isinstance(al, dict) else {}, description=str(d.get("description") or ""),
                      config_id=config_id, config_name=config_name, mapping=d.get("mapping") if isinstance(d.get("mapping"), dict) else {})


class Resolver:
    """한 번 읽은 자료 정의 · 데이터셋 목록으로 여러 이름을 찾는다(계산 실행 · 이벤트 하나 동안 같은 답)."""

    def __init__(self, session: Session, specs: list[dict[str, Any]] | None = None):
        """specs 를 주면 활성 구성 대신 그 자료 정의로 찾는다(올리기 전 미리보기)."""
        self.session = session
        self._specs: dict[str, SourceSpec] | None = None
        if specs is not None:
            self._specs = {norm(sp.name): sp for sp in (spec_from(d) for d in specs if isinstance(d, dict) and d.get("name"))}
        self._datasets: list[Dataset] | None = None
        self._latest: dict[str, Any] | None = None
        self._cache: dict[str, Dataset | None] = {}

    # ── 읽기 ──
    @property
    def specs(self) -> dict[str, SourceSpec]:
        if self._specs is None:
            out: dict[str, SourceSpec] = {}
            for cfg in self.session.execute(select(BusinessConfig).where(BusinessConfig.status == "active").order_by(BusinessConfig.id)).scalars():
                for d in (cfg.content or {}).get("sources") or []:
                    if isinstance(d, dict) and d.get("name"):
                        sp = spec_from(d, cfg.id, cfg.name)
                        out.setdefault(norm(sp.name), sp)
            self._specs = out
        return self._specs

    @property
    def datasets(self) -> list[Dataset]:
        if self._datasets is None:
            self._datasets = [d for d in self.session.execute(select(Dataset).order_by(Dataset.code)).scalars() if getattr(d, "active", True)]
        return self._datasets

    @property
    def latest(self) -> dict[str, Any]:
        """데이터셋 코드 → 현재 버전의 가장 최근 확정 시각(현재 버전이 없으면 없음)."""
        if self._latest is None:
            out: dict[str, Any] = {}
            for o in ("bank", "ext"):
                t = source(o)
                q = select(t.version.dataset_code, func.max(t.version.committed_at)).where(t.version.is_current, t.version.status == "committed").group_by(t.version.dataset_code)
                for code, at in self.session.execute(q):
                    out[code] = at
            self._latest = out
        return self._latest

    # ── 찾기 ──
    def spec(self, ref: str) -> SourceSpec | None:
        return self.specs.get(norm(ref))

    def _cols(self, d: Dataset) -> set[str]:
        # 이름 · 라벨 · 별칭(에이전트가 라벨을 업무 이름으로 바꿔도 원래 머리글은 별칭에 남는다)
        out = {norm(c.get("name")) for c in d.columns or []} | {norm(c.get("label")) for c in d.columns or [] if c.get("label")}
        for c in d.columns or []:
            out |= {norm(a) for a in c.get("aliases") or [] if a}
        return out

    def candidates(self, sp: SourceSpec) -> list[Dataset]:
        need = {norm(c) for c in sp.columns}
        if not need:
            return [d for d in self.datasets if norm(d.name) == norm(sp.name)]
        return [d for d in self.datasets if need <= self._cols(d)]

    def specs_fitting(self, headers: list[str]) -> list[SourceSpec]:
        """올릴 파일의 머리글이 필요한 열을 모두 가진 자료 정의 — 이 파일은 그 자료로 쓰일 모양이다."""
        hs = {norm(h) for h in headers if h}
        return [sp for sp in self.specs.values() if sp.columns and {norm(c) for c in sp.columns} <= hs]

    def breaks_spec(self, d: Dataset, headers: list[str]) -> SourceSpec | None:
        """이 파일을 정의 d 의 새 판으로 넣으면 업무 구성이 못 찾는 경우 — 파일은 자료 정의 모양인데 d 는 아니다(예전 시드 · 다른 양식으로 만든 정의).
        그때는 d 에 넣지 않고 파일에서 새 정의를 만들어야 업무 화면 지표 · 흐름이 이 자료를 읽는다."""
        cols = self._cols(d)
        for sp in self.specs_fitting(headers):
            if not {norm(c) for c in sp.columns} <= cols:
                return sp
        return None

    def _score(self, sp: SourceSpec, d: Dataset) -> tuple[int, int, str]:
        hay = norm(d.name) + " " + norm(d.code) + " " + norm(getattr(d, "file_pattern", "") or "")
        hits = sum(1 for k in sp.keywords if norm(k) and norm(k) in hay) + (2 if norm(d.name) == norm(sp.name) else 0)
        at = self.latest.get(d.code)
        return hits, 1 if at is not None else 0, at.isoformat() if at is not None else ""

    def resolve(self, ref: str | None) -> Dataset | None:
        if not ref:
            return None
        ref = str(ref)
        if ref in self._cache:
            return self._cache[ref]
        found: Dataset | None = None
        d = self.session.get(Dataset, ref)
        if d is not None and getattr(d, "active", True):
            found = d
        else:
            sp = self.spec(ref)
            cands = self.candidates(sp) if sp else [x for x in self.datasets if norm(x.name) == norm(ref)]
            if cands:
                found = max(cands, key=lambda x: self._score(sp, x)) if sp else cands[0]
        self._cache[ref] = found
        return found

    def aliases(self, ref: str, ds: Dataset) -> dict[str, str]:
        """코드용 열 별칭 — 그 이름의 자료 정의, 코드로 가리켰으면 그 정의로 이어지는 자료 정의들의 별칭."""
        sp = self.spec(ref)
        if sp is not None:
            return dict(sp.aliases)
        out: dict[str, str] = {}
        for s in self.specs.values():
            if s.aliases and self.resolve(s.name) is ds:
                out.update({k: v for k, v in s.aliases.items() if k not in out})
        return out

    def mappings_for(self, code: str) -> list[dict[str, Any]]:
        """이 데이터셋으로 이어진 자료 정의들의 온톨로지 연결."""
        return [s.mapping for s in self.specs.values() if s.mapping and (d := self.resolve(s.name)) is not None and d.code == code]

    def refs_for(self, code: str) -> set[str]:
        """이 데이터셋을 가리키는 이름들(코드 포함) — 흐름 조건 · 지표 계보 · 그래프가 이벤트의 데이터셋 코드와 비교할 때."""
        out = {code}
        for s in self.specs.values():
            d = self.resolve(s.name)
            if d is not None and d.code == code:
                out.add(s.name)
        d = self.session.get(Dataset, code)
        if d is not None and d.name:
            out.add(d.name)
        return out

    def status(self) -> list[dict[str, Any]]:
        """자료 정의마다 연결 상태 — 연결됨(데이터셋) · 자료 대기(가장 가까운 정의와 없는 열)."""
        out = []
        for s in self.specs.values():
            d = self.resolve(s.name)
            row: dict[str, Any] = {"name": s.name, "config": s.config_name, "configId": s.config_id, "columns": s.columns, "keywords": s.keywords, "description": s.description,
                                   "aliases": dict(s.aliases)}
            if d is not None:
                row |= {"status": "linked", "dataset": d.code, "datasetName": d.name, "hasData": d.code in self.latest}
            else:
                need = {norm(c): c for c in s.columns}
                best, miss = None, list(need.values())
                for x in self.datasets:
                    lack = [c for k, c in need.items() if k not in self._cols(x)]
                    if best is None or len(lack) < len(miss):
                        best, miss = x, lack
                row |= {"status": "waiting", "closest": None if best is None or len(miss) == len(need) else {"dataset": best.code, "datasetName": best.name, "missingColumns": miss[:12]}}
            out.append(row)
        return out


def resolve(session: Session, ref: str | None) -> Dataset | None:
    return Resolver(session).resolve(ref)


def refs_for(session: Session, code: str) -> set[str]:
    return Resolver(session).refs_for(code)
