"""기본 업무 구성(제품에 포함) — 3개 부서(종합기획부 · 신용리스크관리부 · 영업점) 화면 · 업무 흐름 · 지표 산식 · 화면 연결 · 규칙 · 조직 · 화면 권한.

값은 없다 — 화면 틀은 값 없는 틀로 게시하고, 수치 · 표 · 차트는 올린 원천 자료를 지표 산식으로 계산 커널이 채운다(자료가 없으면 비어 있음).
원천은 자료 이름 · 필요한 열로 실행 때마다 찾는다(data.sources — 자료가 아직 없으면 '자료 대기', 올라오면 이어짐).
기동(시드) 때 반영하고, 제품 판이 바뀌었을 때만(내용 해시) 다시 반영한다 — 관리자가 고친 지표 · 규칙은 같은 판에서는 그대로 둔다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
PACK_NAME = "기본 업무 구성"
PACK_FILE = os.path.join(os.path.dirname(__file__), "business_pack.json")


@lru_cache(maxsize=1)
def _raw() -> bytes:
    with open(PACK_FILE, "rb") as fh:
        return fh.read()


def load_pack() -> dict[str, Any]:
    b = json.loads(_raw().decode("utf-8"))
    b["name"] = PACK_NAME
    return b


def pack_sha() -> str:
    return hashlib.sha256(_raw()).hexdigest()


def seed_business_pack(session: Session, out: dict[str, Any]) -> None:
    """기본 업무 구성 반영 — 같은 판이면 건너뛴다. 예전에 파일로 올린 시연 구성은 이 구성이 이어받는다(항목은 지우지 않고 소유만 옮김)."""
    from nhdip.bizconfig.apply import active_configs, apply, current

    cur = current(session, PACK_NAME)
    if cur is not None and cur.sha256 == pack_sha():
        out["business_pack"] = {"version": cur.version, "status": "same"}
        return
    for c in active_configs(session):
        if c.name != PACK_NAME:
            c.status = "superseded"  # 같은 코드의 지표 · 화면 · 흐름은 아래 반영이 이어받는다(소유 기록이 옮겨감)
    session.flush()
    cfg = apply(session, load_pack(), actor="seed", file_name="business_pack.json", content=_raw())
    out["business_pack"] = {"version": cfg.version, "status": "applied"}
