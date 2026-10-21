"""Neo4j 드라이버 — 그래프는 투영(projection)이며 원장은 PostgreSQL 이다. 장애 시 기능은 축소 동작한다."""
from __future__ import annotations

import logging
import re
import threading
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError, ServiceUnavailable

from nhdip.config import get_settings

logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # 아직 생성 전인 관계 유형 경고 등은 무시

_driver = None
_lock = threading.Lock()
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,60}$")


class GraphUnavailable(RuntimeError):
    pass


def driver():
    global _driver
    with _lock:
        if _driver is None:
            s = get_settings()
            _driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password), connection_timeout=5, max_connection_lifetime=600)
        return _driver


def run(cypher: str, **params: Any) -> list[dict[str, Any]]:
    # DriverError — 연결이 끊긴 세션(SessionExpired) · 커밋 불명(IncompleteCommit) 등 드라이버 오류. ServiceUnavailable · Neo4jError 와
    # 다른 갈래라 따로 잡는다 — Neo4j 가 재시작 · 대량 삭제 중이면 풀의 끊긴 연결에서 나며, 잡지 않으면 화면이 500 이 된다(그래프는 축소 동작이 맞다)
    try:
        with driver().session() as s:
            return [r.data() for r in s.run(cypher, **params)]
    except (ServiceUnavailable, Neo4jError, DriverError, OSError) as exc:
        raise GraphUnavailable(f"{type(exc).__name__}: {exc}") from exc


def safe_name(name: str) -> str:
    """라벨·관계 이름은 파라미터화할 수 없으므로 형식 검증 후 사용한다."""
    if not NAME_RE.match(name or ""):
        raise ValueError(f"허용되지 않는 그래프 이름: {name!r}")
    return name


def health() -> dict[str, Any]:
    try:
        rows = run("MATCH (n) RETURN count(n) AS nodes")
        rels = run("MATCH ()-[r]->() RETURN count(r) AS rels")
        return {"ok": True, "nodes": rows[0]["nodes"], "relationships": rels[0]["rels"]}
    except GraphUnavailable as exc:
        return {"ok": False, "error": str(exc)[:300]}
