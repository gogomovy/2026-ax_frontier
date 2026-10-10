"""비밀번호 해시 · 세션 토큰 서명 · 설정값(LLM 키 등) 암호화."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from nhdip.config import get_settings


# ── 비밀번호 (bcrypt) ────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def password_policy_error(password: str) -> str | None:
    """간단한 정책: 8자 이상, 영문·숫자 포함, 72바이트 이하(bcrypt 한계)."""
    if len(password) < 8:
        return "비밀번호는 8자 이상이어야 합니다."
    if len(password.encode("utf-8")) > 72:
        return "비밀번호가 너무 깁니다(72바이트 이하)."
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "비밀번호는 영문과 숫자를 모두 포함해야 합니다."
    return None


# ── 세션 토큰 (HMAC 서명) ────────────────────────────────────
def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _sign(value: str) -> str:
    key = get_settings().session_secret.encode("utf-8")
    return base64.urlsafe_b64encode(hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()).decode().rstrip("=")


def sign_session(session_id: str) -> str:
    return f"{session_id}.{_sign(session_id)}"


def unsign_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    sid, sig = token.rsplit(".", 1)
    return sid if hmac.compare_digest(sig, _sign(sid)) else None


def session_hash(session_id: str) -> str:
    """DB 에는 세션 ID 원문 대신 해시를 저장한다."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


# ── 설정값 암호화 (AES-256-GCM) ──────────────────────────────
def _aes_key() -> bytes:
    raw = get_settings().config_enc_key
    if raw:
        try:
            key = base64.b64decode(raw)
            if len(key) == 32:
                return key
        except ValueError:
            pass
        return hashlib.sha256(raw.encode("utf-8")).digest()
    # 키 미설정(개발) — 세션 비밀에서 파생
    return hashlib.sha256(("enc:" + get_settings().session_secret).encode("utf-8")).digest()


def encrypt_secret(plain: str) -> str:
    if not plain:
        return ""
    nonce = os.urandom(12)
    ct = AESGCM(_aes_key()).encrypt(nonce, plain.encode("utf-8"), b"nhdip-cfg")
    return "v1:" + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(token: str | None) -> str:
    if not token:
        return ""
    if not token.startswith("v1:"):
        raise ValueError("unknown secret format")
    blob = base64.b64decode(token[3:])
    return AESGCM(_aes_key()).decrypt(blob[:12], blob[12:], b"nhdip-cfg").decode("utf-8")


def mask_secret(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) <= 8:
        return "•" * len(plain)
    return f"{plain[:4]}{'•' * 8}{plain[-4:]}"
