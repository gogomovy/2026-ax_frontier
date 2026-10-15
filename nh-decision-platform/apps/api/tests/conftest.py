"""테스트 환경 — 통합 테스트는 별도 DB(<기본DB>_test)를 만들어 쓴다. 운영 그래프를 건드리지 않도록 Neo4j 는 끈다."""
import os

import psycopg
import pytest

BASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://nhdip:nhdip@localhost:5432/nhdip")
_db = BASE_URL.rsplit("/", 1)[1]
TEST_DB = f"{_db}_test"
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/" + TEST_DB

os.environ["DATABASE_URL"] = TEST_URL
os.environ["NEO4J_URI"] = "bolt://127.0.0.1:1"  # 그래프 장애 경로(축소 동작) 검증
os.environ.setdefault("SESSION_SECRET", "test-secret-test-secret-test-secret")
os.environ["BOOTSTRAP_ADMIN_EMP_NO"] = "00000001"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "Admin1234!"
os.environ["FILESTORE_DIR"] = "/tmp/nhdip-test-files"
os.environ["LLM_DEFAULT_MODEL"] = ""
os.environ["LLM_DEFAULT_BASE_URL"] = "http://llm.test:4000"  # 시드 연결 주소(호출은 각 테스트가 가짜로 대체) — 기본값은 비어 있음(B.36)
os.environ["NHDIP_USE_APP_ROLE"] = "0"  # 테스트 DB 는 소유자 계정으로 (앱 계정 권한은 test_app_role 에서 따로 검증)


def _pg_available() -> bool:
    try:
        with psycopg.connect(BASE_URL.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


PG = _pg_available()


@pytest.fixture(scope="session")
def db():
    if not PG:
        pytest.skip("PostgreSQL 없음 — 통합 테스트 생략")
    admin = BASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{TEST_DB}"')
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    command.upgrade(cfg, "head")
    from nhdip.db import SessionLocal
    from nhdip.seed.run import run_seed

    with SessionLocal() as s:
        run_seed(s, with_precompute=True)  # 정의만 (Phase I · Q135)
    # 시연 자료 패키지(엑셀 · CSV · PDF)를 실제 업로드 엔드포인트로 올린다 (Q137) — 이후 시험은 업로드된 자료 위에서 돈다
    from fastapi.testclient import TestClient

    from nhdip.main import app
    from nhdip.sample.build import build
    from nhdip.sample.load import upload_http

    rep = upload_http("http://testserver", "00000001", "Admin1234!", build(), client=TestClient(app))
    assert rep.ok, rep.failed
    yield SessionLocal


def drain_workflows(SessionLocal, rounds: int = 6, per_round: int = 60) -> int:
    """워커 대신 — 미처리 이벤트를 디스패치하고 대기 작업을 모두 실행(디바운스 무시). 처리한 작업 수."""
    from sqlalchemy import select

    from nhdip.models import Job, utcnow
    from nhdip.worker import process_one
    from nhdip.workflow.dispatcher import dispatch_once

    total = 0
    for _ in range(rounds):
        with SessionLocal() as s:
            dispatch_once(s)
            for j in s.execute(select(Job).where(Job.status == "queued")).scalars():
                j.run_after = utcnow()
            s.commit()
        n = 0
        while n < per_round and process_one("test"):
            n += 1
        total += n
        if n == 0:
            break
    return total


@pytest.fixture(scope="session")
def computed(db):
    """업로드 이벤트로 걸린 워크플로를 모두 돌린 상태 — 화면 산출물이 자료로 계산돼 있다(실제 업로드 뒤와 같음).
    계산 전 값 없는 틀은 화면 · 색인에서 걸러지므로(M.19 · Q204) 분석 결과를 전제로 하는 시험은 이 fixture 를 쓴다."""
    drain_workflows(db)
    # 워커의 주기 대조(run_maintenance → reconcile)와 같이 — 자료가 생겨 색인 지문이 바뀌면 전체를 다시 색인한다(M.21 · Q207)
    from nhdip.knowledge.maintenance import reconcile

    with db() as s:
        reconcile(s)
        s.commit()
    return db


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """테스트마다 속도 제한 창을 비운다 — 같은 IP(testclient)로 여러 번 로그인하므로."""
    from nhdip import ratelimit
    from nhdip.llm import breaker, budget

    ratelimit.reset()
    breaker.reset()  # LLM 연결 차단기(프로세스 메모리)도 시험마다 비운다 — 앞 시험의 의도된 실패가 뒤 시험의 호출을 막지 않게
    budget.clear_cache()
    yield
