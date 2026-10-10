"""DB 엔진·세션. 원장(System of Record)은 PostgreSQL 이다."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from nhdip.config import get_settings

# 설계 §19.4 — iam(사용자·조직·권한) · cfg(관리자 설정) · bank/ext(출처별 원천) · calc(계산 이력)
#              app(화면 산출물·사용자 상태) · ops(큐·실행 기록) · audit(감사) · mart(컬럼 정의서 기반 화면 테이블)
SCHEMAS = ("iam", "cfg", "bank", "ext", "calc", "app", "ops", "audit", "mart")

_settings = get_settings()
# 트랜잭션을 연 채 멈춘 연결(잠금 보유)을 DB 가 끊도록 — 0 이면 끄기 (B.32 · 환경변수 DB_IDLE_TX_TIMEOUT_MS)
_connect_args = {"options": f"-c idle_in_transaction_session_timeout={int(_settings.db_idle_tx_timeout_ms)}"} if _settings.db_idle_tx_timeout_ms and _settings.database_url.startswith("postgresql") else {}
engine = create_engine(_settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20, future=True, connect_args=_connect_args)
# 관측성 — 범위(요청 · 작업)별 질의 수 · 소요 합산 (작업 0.5)
from nhdip.obs import instrument_engine  # noqa: E402

instrument_engine(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI 의존성 — 요청 단위 세션. 커밋은 핸들러에서 명시적으로 한다."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
