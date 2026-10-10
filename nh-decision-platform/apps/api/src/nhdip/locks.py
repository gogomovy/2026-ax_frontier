"""PostgreSQL 권고 잠금(advisory lock) — 같은 대상에 대한 동시 쓰기를 직렬화한다 (B.32).

트랜잭션 잠금(xact)이라 commit · rollback 때 자동으로 풀린다. 이름은 64비트 해시(hashtextextended)로 바꿔 쓴다.
  lock(session, "artifact:risk_dashboard")     — 잡힐 때까지 기다린다 (산출물 게시 · 데이터셋 버전 · 사용자 상태)
  try_lock(session, "workflow:wf_x")           — 못 잡으면 False (작업 가져가기 — 다른 워커가 같은 워크플로우를 잡는 중)
PostgreSQL 이 아닌 DB(테스트용 등)에서는 아무것도 하지 않는다.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def _pg(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def lock(session: Session, name: str) -> None:
    if _pg(session):
        session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:n, 0))"), {"n": name})


def try_lock(session: Session, name: str) -> bool:
    if not _pg(session):
        return True
    return bool(session.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended(:n, 0))"), {"n": name}).scalar())
