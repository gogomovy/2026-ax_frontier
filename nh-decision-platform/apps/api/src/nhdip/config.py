"""런타임 설정 (환경 변수). 업무 설정(LLM·워크플로우·데이터셋 등)은 DB `cfg.*` 에서 관리한다."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    nhdip_env: str = "dev"
    database_url: str = "postgresql+psycopg://nhdip:nhdip@localhost:5432/nhdip"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "nhdip-neo4j"

    filestore_dir: str = "/data/files"

    session_secret: str = "dev-session-secret-change-me-dev-session-secret"
    config_enc_key: str = ""  # base64 32바이트 (AES-256-GCM)
    cookie_secure: bool = False
    session_cookie: str = "nhdip_session"
    session_ttl_hours: int = 12
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
