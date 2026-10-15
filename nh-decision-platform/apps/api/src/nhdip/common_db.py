"""공통 통합 DB (요구사항 §38 CMN) — 종기부 · 사업부서 · 영업본부 · 영업점이 함께 보는 자료.

무엇이 공통인가
  정형   데이터셋 정의의 common=true (관리자 [데이터셋·문서]에서 켬). 판의 소유 팀은 늘 비운다(전행 공통) — 팀 업로드가 덮어쓰지 않는다
  문서   문서 분류가 설정 common.doc_classes(기본 common_ref '공통 통합 자료')인 문서. 소유 팀 없음

누가 올리나
  관리자만. 업무 사용자 · 부서 데이터 책임자의 자료 올리기 · 자료 등록 · 승인은 공통 자료를 대상으로 하지 못한다(목록에서도 빠진다)

어디에 쓰이나 (자료가 올라오면 저절로)
  ① PostgreSQL 원장(bank/ext) — 소유 없음이라 모든 부서 화면의 [데이터베이스] 목록에 보인다
  ② 근거 검색 · 근거 붙이기 — 모든 부서 흐름이 자기 문서 분류 + 공통 문서 분류를 함께 찾는다
  ③ 질의(AI 어시스턴트) — 공통 자료 설명 카드는 컬렉션 catalog.common(전행 공개)
  ④ 온톨로지 — 공통 자료의 키(상품코드 · 사무소코드 · 등급 …)를 다른 부서 자료의 열이 가리키면 '참조' 관계를 제안하고(구축 에이전트),
     승인되면 Neo4j 에 부서 자료 → 공통 개체 관계가 생긴다(부서 사이의 새 연관)
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from nhdip.models import Dataset, Setting

DEFAULT_DOC_CLASSES = ["common_ref"]
CATALOG_COLLECTION = "catalog.common"


class CommonOnly(PermissionError):
    """공통 통합 DB 는 관리자만 올린다."""


def common_doc_classes(session: Session) -> list[str]:
    s = session.get(Setting, "common.doc_classes")
    v = s.value if s is not None else None
    return [str(x) for x in v] if isinstance(v, list) else list(DEFAULT_DOC_CLASSES)


def is_common_doc_class(session: Session, doc_class: str | None) -> bool:
    return bool(doc_class) and doc_class in common_doc_classes(session)


def is_common(ds: Any) -> bool:
    return bool(getattr(ds, "common", False))


def common_codes(session: Session) -> set[str]:
    return set(session.execute(select(Dataset.code).where(Dataset.common.is_(True), Dataset.active)).scalars())


def assert_can_upload(user: Any, *, dataset: Any = None, doc_class: str | None = None, session: Session | None = None) -> None:
    """관리자가 아니면 공통 자료(데이터셋 · 문서 분류)를 올리지 못한다."""
    if getattr(user, "role", None) == "admin":
        return
    if dataset is not None and is_common(dataset):
        raise CommonOnly("공통 통합 DB 자료는 관리자만 올릴 수 있습니다")
    if doc_class and session is not None and is_common_doc_class(session, doc_class):
        raise CommonOnly("공통 통합 DB 문서는 관리자만 올릴 수 있습니다")


def summary(session: Session) -> dict[str, Any]:
    """관리자 화면 요약 — 공통 데이터셋(현재 판 · 행) · 공통 문서 수 · 온톨로지 참조 관계."""
    from nhdip.data.datasets import current_versions
    from nhdip.models import OntologySchema, source

    items = []
    for d in session.execute(select(Dataset).where(Dataset.common.is_(True)).order_by(Dataset.code)).scalars():
        cvs = current_versions(session, d)
        items.append({"code": d.code, "name": d.name, "kind": d.kind, "origin": d.origin, "active": d.active, "versions": len(cvs), "rows": sum(int(v.row_count or 0) for v in cvs),
                      "asOf": max((v.as_of for v in cvs if v.as_of), default=None)})
    classes = common_doc_classes(session)
    docs = 0
    for o in ("bank", "ext"):
        t = source(o)
        docs += len(session.execute(select(t.document.id).where(t.document.is_current, t.document.doc_class.in_(classes or [""]))).all())
    schema = session.execute(select(OntologySchema).where(OntologySchema.active)).scalar()
    refs = [r for r in (schema.relations if schema else []) or [] if (r.get("type") or "").startswith("REFERS_")]
    for it in items:
        if it["asOf"] is not None:
            it["asOf"] = it["asOf"].isoformat()
    return {"datasets": items, "docClasses": classes, "documents": docs,
            "references": [{"type": r.get("type"), "ko": r.get("ko"), "to": r.get("to"), "datasets": sorted({str(b.get("dataset")) for b in r.get("backing") or []})} for r in refs]}
