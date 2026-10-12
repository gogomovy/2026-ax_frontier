"""iam — 조직(부/국/팀) · 사용자(사번) · 화면 · 화면 권한 · 세션 (설계 §19.4, §19.7)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


class OrgUnit(Base):
    __tablename__ = "org_unit"
    __table_args__ = {"schema": "iam"}

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # 트리 깊이(1=최상위). 상위 조직 기준으로 자동 계산한다
    level: Mapped[int] = mapped_column(Integer)
    # 조직 유형 — 본부 · 부 · 국 · 팀 · 지역본부 · 영업점 (정의·허용 상위 유형은 cfg.setting 'org.unit_types')
    unit_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("iam.org_unit.code"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = {"schema": "iam"}

    emp_no: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(100))
    org_code: Mapped[str] = mapped_column(ForeignKey("iam.org_unit.code"))
    position: Mapped[str | None] = mapped_column(String(30), nullable=True)
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin | user
    # 부서 데이터 책임자 (UPL-04 · Q107) — 자기 부서(가장 가까운 부 · 지역본부) 사용자의 자료 요청을 승인 · 반려
    data_steward: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending|active|locked|disabled
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Screen(Base):
    __tablename__ = "screen"
    __table_args__ = {"schema": "iam"}

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    path: Mapped[str] = mapped_column(String(200))
    label: Mapped[str] = mapped_column(String(100))
    # 메뉴 묶음 (예: 종합기획부 / 신용리스크관리부 / 영업점 / 공통 / 관리자)
    section: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(12), default="flow")  # flow | reference | admin | hidden
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    count_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    match: Mapped[str | None] = mapped_column(Text, nullable=True)  # 활성 판정 접두어(쉼표 구분)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    admin_only: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ScreenGrant(Base):
    __tablename__ = "screen_grant"
    __table_args__ = {"schema": "iam"}

    org_code: Mapped[str] = mapped_column(ForeignKey("iam.org_unit.code", ondelete="CASCADE"), primary_key=True)
    screen_code: Mapped[str] = mapped_column(ForeignKey("iam.screen.code", ondelete="CASCADE"), primary_key=True)
    granted_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(default=utcnow)


class UserSession(Base):
    __tablename__ = "session"
    __table_args__ = {"schema": "iam"}

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    emp_no: Mapped[str] = mapped_column(ForeignKey("iam.app_user.emp_no", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
