"""Neo4j 드라이버 오류는 화면 500 이 아니라 그래프 축소 동작으로 — 끊긴 세션(SessionExpired) · 커밋 불명 같은 DriverError 도 같이 잡는다."""
from __future__ import annotations

import pytest
from neo4j.exceptions import IncompleteCommit, ServiceUnavailable, SessionExpired


class _Boom:
    def __init__(self, exc: Exception):
        self.exc = exc

    def session(self):
        raise self.exc


@pytest.mark.parametrize("exc", [SessionExpired("세션 끊김"), IncompleteCommit("커밋 불명"), ServiceUnavailable("연결 안 됨"), OSError("소켓")])
def test_driver_errors_degrade(monkeypatch, exc):
    from nhdip.graph import neo4j_client as g

    monkeypatch.setattr(g, "driver", lambda: _Boom(exc))
    with pytest.raises(g.GraphUnavailable):
        g.run("RETURN 1")
    h = g.health()
    assert h["ok"] is False and type(exc).__name__ in h["error"]
