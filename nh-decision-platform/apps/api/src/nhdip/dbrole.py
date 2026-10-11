"""API 전용 DB 계정 (B.33) — 네트워크에 노출된 api 는 데이터 조작(DML)만 할 수 있는 계정으로 접속한다.

- 테이블 소유자(마이그레이션 · 시드 · 워커의 정의서 테이블 생성)는 기존 계정(POSTGRES_USER)이 맡는다.
- 앱 계정은 스키마 사용 + 표 조회 · 추가 · 수정 · 삭제만. 감사 로그(audit.*)는 조회 · 추가만 —
  소유자가 아니므로 감사 로그의 추가 전용 트리거를 끄거나(ALTER TABLE) 표를 비우거나(TRUNCATE) 지울 수 없다.
- 앞으로 소유자가 만드는 표에도 같은 권한이 붙도록 기본 권한(ALTER DEFAULT PRIVILEGES)을 둔다.
켜기: `.env` 의 APP_DB_PASSWORD (make env 가 생성). 비우면 api 도 소유자 계정으로 접속한다(이전 방식).
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nhdip.db import SCHEMAS

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def ensure_app_role(engine: Engine, user: str, password: str) -> list[str]:
    """앱 계정 생성 · 비밀번호 · 권한 부여 (멱등). 반환: 수행한 단계 요약."""
    if not _IDENT.match(user):
        raise ValueError(f"앱 계정 이름 형식 오류: {user}")
    done: list[str] = []
    with engine.begin() as c:
        owner = c.execute(text("SELECT current_user")).scalar()
        db = c.execute(text("SELECT current_database()")).scalar()
        exists = c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": user}).scalar()
        # 비밀번호는 식별자 · 리터럴 바인딩이 안 되는 DDL 이라 따옴표를 이스케이프해 넣는다
        pw = password.replace("'", "''")
        # text() 는 ':이름' 을 바인딩으로 읽으므로 드라이버 SQL 로 보낸다(psycopg 는 매개변수가 없으면 % 를 해석하지 않음)
        if not exists:
            c.exec_driver_sql(f"CREATE ROLE {user} LOGIN PASSWORD '{pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT")
            done.append("create role")
        else:
            c.exec_driver_sql(f"ALTER ROLE {user} WITH LOGIN PASSWORD '{pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        c.execute(text(f'GRANT CONNECT ON DATABASE "{db}" TO {user}'))
        for sch in SCHEMAS:
            if not c.execute(text("SELECT 1 FROM pg_namespace WHERE nspname = :s"), {"s": sch}).scalar():
                continue
            c.execute(text(f"GRANT USAGE ON SCHEMA {sch} TO {user}"))
            c.execute(text(f"REVOKE CREATE ON SCHEMA {sch} FROM {user}"))
            c.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {sch} TO {user}"))
            c.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA {sch} GRANT USAGE, SELECT ON SEQUENCES TO {user}'))
            if sch == "audit":
                c.execute(text(f"REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA {sch} FROM {user}"))
                c.execute(text(f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA {sch} TO {user}"))
                c.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA {sch} GRANT SELECT, INSERT ON TABLES TO {user}'))
            else:
                c.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {sch} TO {user}"))
                c.execute(text(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA {sch} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {user}'))
        c.execute(text(f"REVOKE CREATE ON SCHEMA public FROM {user}"))
        done.append(f"grants({len(SCHEMAS)} schemas, owner={owner})")
    return done
