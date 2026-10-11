"""런타임 설정 (환경 변수). 업무 설정(LLM·워크플로우·데이터셋 등)은 DB `cfg.*` 에서 관리한다."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    nhdip_env: str = "dev"
    database_url: str = "postgresql+psycopg://nhdip:nhdip@localhost:5432/nhdip"
    # API 전용 DB 계정 (B.33) — 비밀번호가 있으면 이 계정(DML 만)으로 접속. 마이그레이션 · 시드 · 워커는 NHDIP_USE_APP_ROLE=0 으로 소유자 계정
    app_db_user: str = "nhdip_app"
    app_db_password: str = ""
    nhdip_use_app_role: bool = True
    db_idle_tx_timeout_ms: int = 0  # 트랜잭션 유휴 제한(ms) — 0 이면 끄기. compose 기본 600000 (B.32)

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "nhdip-neo4j"

    filestore_dir: str = "/data/files"

    session_secret: str = "dev-session-secret-change-me-dev-session-secret"
    config_enc_key: str = ""  # base64 32바이트 (AES-256-GCM)
    cookie_secure: bool = False
    session_cookie: str = "nhdip_session"
    session_ttl_hours: int = 12
    # 변경 요청(POST 등)의 Origin 허용 목록(쉼표 구분, 예: https://nhdip.example). 비우면 요청 Host 와 같은 출처만 허용 (B.32)
    trusted_origins: str = ""
    # X-Forwarded-For 를 믿을 바로 앞 프록시(쉼표, CIDR 또는 호스트 이름) — 기본: 이 컴퓨터 + compose 의 web 컨테이너 (B.33)
    trusted_proxies: str = "127.0.0.1/32,::1/128,web"
    # 신뢰 프록시가 몇 겹인지 — 1 = Next(web) 가 붙인 값 하나. 앞에 사내 L7 프록시가 하나 더 있으면 2
    trusted_proxy_hops: int = 1
    # API 문서(/docs · /openapi.json) — 비우면 dev 에서만 켠다. true/false 로 강제
    api_docs: str = ""
    # SSO(OIDC · Authorization Code + PKCE) — issuer 를 비우면 꺼짐 (F.13 · AUTH-01)
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""  # 예: https://<웹 주소>/backend/auth/oidc/callback
    oidc_scopes: str = "openid profile"
    oidc_emp_claim: str = "emp_no"  # 사번이 담긴 ID 토큰 클레임
    oidc_label: str = "사내 통합 로그인(SSO)"
    oidc_local_login: str = "all"  # all · admin(관리자 비상 로그인만) · none

    bootstrap_admin_emp_no: str = "00000001"
    bootstrap_admin_password: str = ""

    llm_default_base_url: str = "http://litellm:4000"
    llm_default_api_key: str = ""
    llm_default_model: str = ""

    as_of_default: str = "2026-08-31"
    seed_dir: str = ""  # 비우면 패키지 내장 seed 디렉터리

    worker_poll_sec: float = 1.0
    embedding_dim: int = 1024


def runtime_database_url(st: "Settings") -> str:
    """실행 시 접속 주소 — 앱 계정 비밀번호가 있고 쓰기로 했으면 같은 DB 에 앱 계정으로 (B.33)."""
    if not (st.nhdip_use_app_role and st.app_db_password):
        return st.database_url
    from sqlalchemy.engine import make_url

    return make_url(st.database_url).set(username=st.app_db_user, password=st.app_db_password).render_as_string(hide_password=False)


DEFAULT_SESSION_SECRET = Settings.model_fields["session_secret"].default


def check_runtime(st: Settings) -> None:
    """운영 기동 전 점검 (B.32) — 기본 비밀값으로 운영 기동을 거부한다."""
    if st.nhdip_env == "prod" and (st.session_secret == DEFAULT_SESSION_SECRET or len(st.session_secret) < 32):
        raise RuntimeError("운영(NHDIP_ENV=prod)에서는 32자 이상의 SESSION_SECRET 이 필요합니다 (make env)")


def docs_enabled(st: Settings) -> bool:
    v = st.api_docs.strip().lower()
    return v in ("1", "true", "yes", "on") if v else st.nhdip_env != "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
