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
# 시드는 플랫폼만(Phase O) — 시험 DB 는 실제 사용자처럼 시연 업무 구성 파일 + 시연 자료 27개 + 문서를 올린 위에서 돈다.
# CODES: 시나리오 자료 구분(예전 데이터셋 코드) → 파일에서 만들어진 데이터셋 코드
CODES: dict[str, str] = {}


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
        run_seed(s, with_precompute=True)  # 플랫폼만 (Phase O)
    # 시연 업무 구성 파일 · 시연 자료 패키지(엑셀 · CSV · PDF)를 실제 업로드 엔드포인트로 올린다 (Q137 · Phase O)
    from fastapi.testclient import TestClient

    from nhdip.main import app
    from nhdip.sample.build import build
    from nhdip.sample.load import upload_http

    pkg = build()
    c = TestClient(app)
    rep = upload_http("http://testserver", "00000001", "Admin1234!", pkg, client=c, config=True)
    assert rep.ok, rep.failed
    CODES.update(rep.codes)
    _contract_expected(SessionLocal)
    yield SessionLocal


def _contract_expected(SessionLocal) -> None:
    """정의서 시연 화면값(PDF 기준 기대값)은 업무 구성 파일에 넣지 않는다(M.22 · Q209) — 시험 DB 만 넣어 계산과 대조한다."""
    import json

    from sqlalchemy import select

    from nhdip.models import ColumnContract

    with open(os.path.join(os.path.dirname(__file__), "fixtures", "contract_expected.json"), encoding="utf-8") as fh:
        rows = json.load(fh)
    with SessionLocal() as s:
        by = {(c.table_code, c.column_name): c for c in s.execute(select(ColumnContract)).scalars()}
        for r in rows:
            c = by.get((r["table_code"], r["column_name"]))
            if c is None:
                continue
            c.expected_text = r.get("expected_text")
            if r.get("expected"):
                c.binding = {**(c.binding or {}), "expected": r["expected"], **({"expected_note": r["expected_note"]} if r.get("expected_note") else {})}
        s.commit()


def code_of(kind: str) -> str:
    """시나리오 자료 구분(예: PROVISION_BY_PRODUCT) → 시연 파일을 올려 만들어진 데이터셋 코드."""
    return CODES.get(kind, kind)


def aliases_of(session, kind: str) -> dict[str, str]:
    """코드용 값 이름 → 파일의 열 이름 — 그 자료로 이어진 업무 구성 '자료'의 별칭(Phase O · BIZ-03)."""
    from nhdip.data.sources import Resolver
    from nhdip.models import Dataset

    code = code_of(kind)
    ds = session.get(Dataset, code)
    return Resolver(session).aliases(code, ds) if ds is not None else {}


def to_cols(session, kind: str, rows: list[dict]) -> list[dict]:
    """시험이 코드용 이름으로 만든 행 → 파일에서 만든 정의의 열 이름."""
    al = aliases_of(session, kind)
    return [{al.get(k, k): v for k, v in r.items()} for r in rows]


def from_cols(session, kind: str, rows: list[dict]) -> list[dict]:
    """읽은 행에 코드용 이름 열을 더한다(원래 열은 그대로)."""
    inv = {v: k for k, v in aliases_of(session, kind).items()}
    return [{**r, **{inv[k]: v for k, v in r.items() if k in inv}} for r in rows]


def prov_correction_csv(rows: list[dict], *, delta: int = 10_000, plus: str = "2001107820007", minus: str = "2001101010001", extra: list[dict] | None = None) -> bytes:
    """7790 정정본(CSV) — 포용금융 상품 하나에 +delta, 포용금융이 아닌 상품 하나에 −delta(총계 유지). 열은 올라온 정의 그대로.
    (312,470 + 10,000) / 3,412,180 × 100 = 9.4505 → 9.45"""
    from nhdip.sample.build import business_config

    al = next(s["aliases"] for s in business_config()["sources"] if s["name"] == "상품별 충당금(7790)")
    pc, pv = al["product_code"], al["provision"]
    heads = [k for k in rows[0] if not k.startswith("_")]

    def cell(v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return "Y" if v else "N"
        return str(v)

    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(heads)
    for r in [*rows, *(extra or [])]:
        amt = r[pv] + (delta if str(r[pc]) == plus else 0) - (delta if str(r[pc]) == minus else 0) if r.get(pv) is not None else None
        w.writerow([cell(amt if k == pv else r.get(k)) for k in heads])
    return buf.getvalue().encode("utf-8")


def strip_alias(session, kind: str, rows: list[dict]) -> list[dict]:
    """from_cols 로 더한 코드용 이름 열을 뺀다(다시 올릴 때)."""
    al = aliases_of(session, kind)
    extra = {k for k, v in al.items() if k != v}
    return [{k: v for k, v in r.items() if k not in extra} for r in rows]


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
