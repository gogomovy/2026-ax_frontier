"""AI 어시스턴트 대화 기억 — 사용자(사번)별 대화 · 메시지 · 누적 요약.

대화 하나 = 질문 · 답 메시지 묶음. 멀티턴 맥락은 '누적 요약(summary) + 요약되지 않은 메시지 원문'으로 만든다.
맥락이 설정 토큰 수(기본 5만)를 넘으면 오래된 메시지부터 요약에 합치고(summarized_upto 까지는 요약에 들어 있음),
대화를 떠날 때(close) 전체를 요약해 두어 나중에 다시 열면 그 요약으로 이어 간다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utcnow


class AssistConversation(Base):
    __tablename__ = "assist_conversation"
    __table_args__ = (Index("ix_app_assist_conversation_emp_updated", "emp_no", "updated_at"), {"schema": "app"})

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 화면이 만든 대화 id(사용자 범위 안에서만 쓰인다)
    emp_no: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(120), default="새 대화")
    summary: Mapped[str] = mapped_column(Text, default="")  # 누적 요약 — seq ≤ summarized_upto 메시지의 내용
    summary_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summarized_upto: Mapped[int] = mapped_column(Integer, default=0)
    summary_by: Mapped[str | None] = mapped_column(String(12), nullable=True)  # llm | rule
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)  # 떠날 때 전체 요약을 만든 시각


class AssistMessage(Base):
    __tablename__ = "assist_message"
    __table_args__ = (Index("ix_app_assist_message_conv_seq", "conversation_id", "seq", unique=True), {"schema": "app"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("app.assist_conversation.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    text: Mapped[str] = mapped_column(Text, default="")
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    # 답의 화면 표시 · 다음 턴 재료 — 수치 · 출처 · 검증 · 도구 호출(이름 · 조건). 후속 질문이 앞 턴의 집계 조건을 이어받는다
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
