"""NAVI 시나리오 자료 묶음 — 종합기획부 · 사업부서(신용리스크관리부 신용모형팀) · 영업점 3곳이 각자 자기 자료를 올려 발표 흐름 그대로 돌려 보는 묶음.

빈 플랫폼(정의만 있는 상태 · `python -m nhdip.cli reset-data --yes` 뒤)에서 폴더 순서대로 올리면
  종합기획부   현황 · 목표 대비 이탈 · 경영목표 제안 → 목표 확정
  사업부서     모형 모니터링 · 포용금융 충당금 분석 → 수행방안(영업점 참고 켜기)
  영업점       지점 현황 · 우량기업 · 서민금융 영업 가이드(본부 수행방안 · 확정 목표를 근거로)
  영업본부     세 지점 업적평가 통합(순위 · 득점률)
이 차례로 계산된다. 파일 양식 · 열은 시연 자료(sample.build)와 같다 — 같은 자료 정의에 그대로 이어진다.

  python -m nhdip.sample scenario --out test-data/navi-scenario

폴더 · 소유
  00_관리자_공통            소유 없음(전행 공통) — 여러 부서가 같이 쓰는 마스터 · 전행 시스템 추출 · 정부정책 · 영업점 기준 문서
  01_종합기획부              소유 T111 경영목표팀
  02_신용리스크관리부_신용모형팀  소유 T213 신용모형팀(조직표에 없으면 관리자 [조직 관리]에서 리스크측정국(B210) 아래 팀으로 추가)
  03~05_영업점               소유 그 영업점(BR301 · BR302 · BR303)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .branches import BRANCHES, REGION_CODE, REGION_NAME, branch_files, common_versions
from .build import SampleFile, _tidy_files, build


@dataclass(frozen=True)
class Org:
    code: str
    name: str
    unit_type: str
    parent: str | None
    sort: int = 0


# 시나리오가 쓰는 조직 — 기본 조직표(업무 구성)에 있으면 그대로, 없으면(신용모형팀) 관리자가 [조직 관리]에서 추가한다
HQ_TEAM = Org("T111", "경영목표팀", "TEAM", "B110")
RISK_TEAM = Org("T213", "신용모형팀", "TEAM", "B210", 25)
REGION_TEAM = Org("T311", "영업점지원팀", "TEAM", "B310")
NEW_ORGS = (RISK_TEAM,)

# 가입 · 승인 계정(시험용 사번) — (사번, 이름, 소속, 설명)
ACCOUNTS = (
    ("20269101", "종기부시험", HQ_TEAM.code, "종합기획부 경영목표팀"),
    ("20269201", "모형시험", RISK_TEAM.code, "신용리스크관리부 신용모형팀"),
    *((e, n, o, next(f"{b.name}" for b in BRANCHES if b.code == o)) for e, n, o in (("20269301", "강남시험", "BR301"), ("20269302", "서초시험", "BR302"), ("20269303", "역삼시험", "BR303"))),
    ("20269300", "본부시험", REGION_TEAM.code, f"{REGION_NAME} 영업점지원팀"),
)

# 시연 자료(sample.build) 가운데 부서별로 나누는 자료 구분
COMMON_KINDS = ("RETAIL_POOL_MASTER", "OBLG_GRD_DEF", "RETAIL_EXPOSURE")  # 여러 부서 흐름이 같이 읽는 마스터 · 전행 시스템 추출(지점 비교의 전행 기준)
HQ_KINDS = ("PL_PRODUCT_SEGMENT", "LOAN_BALANCE_MONTHLY", "CAPITAL_CONSTRAINT", "PEER_BANK_STATS", "HQ_PLAN_KPI")
RISK_KINDS = ("INCLUSIVE_PRODUCTS", "PD_MASTER_SCALE", "PROVISION_BY_PRODUCT", "MODEL_MONITORING_GRADE", "DEFAULT_RATE_MONTHLY", "RETAIL_POOL_SUMMARY")
# 문서 — 분류 · 문서 코드로 나눈다(정부정책 · 영업점 기준은 공통, 경영 의사결정은 종합기획부, 모형 · 포용금융 운영기준은 사업부서)
RISK_DOCS = {"doc-mgmt-inclusive-products"}
COMMON_DOC_CLASSES = {"gov_policy", "branch_ref"}
DOC_CLASS_KO = {"gov_policy": "정부정책 DB", "mgmt_decision": "경영 의사결정 DB", "model_method": "모형·방법론", "branch_ref": "영업점 기준·공문"}  # 기본 업무 구성의 문서 분류 이름(안내용)
HQ_DOC_CLASSES = {"mgmt_decision"}
RISK_DOC_CLASSES = {"model_method"}


@dataclass
class Folder:
    name: str
    owner: str | None  # 올릴 때 고르는 '자료를 둘 팀 · 영업점'(None = 전행 공통)
    who: str  # 누가 올리는지(안내)
    files: list[SampleFile]


def _by_kind(files: list[SampleFile], kinds: tuple[str, ...]) -> list[SampleFile]:
    order = {k: i for i, k in enumerate(kinds)}
    return sorted((f for f in files if f.kind == "dataset" and f.dataset in order), key=lambda f: (order[f.dataset or ""], f.name))


def folders() -> list[Folder]:
    """업로드 순서대로 — 공통(마스터) → 종합기획부 → 사업부서 → 영업점."""
    base = build().files
    docs = [f for f in base if f.kind == "document"]

    def doc_cls(f: SampleFile) -> str:
        return str((f.doc or {}).get("docClass") or "")

    def doc_code(f: SampleFile) -> str:
        return str((f.doc or {}).get("docCode") or "")

    # 영업점 공통 자료는 이 시나리오의 세 지점으로(사무소 마스터 · 배점표 · Pool 정의 · 본부 추천 가망기업) — 시연 자료의 기본 지점은 넣지 않는다
    branch_common = _tidy_files(common_versions())
    pool = next(f for f in branch_common if f.dataset == "RETAIL_POOL_MASTER")
    common = [pool] + [f for f in _by_kind(base, COMMON_KINDS) if f.dataset != "RETAIL_POOL_MASTER"] + [f for f in branch_common if f.dataset != "RETAIL_POOL_MASTER"]
    common += [f for f in docs if doc_cls(f) in COMMON_DOC_CLASSES]
    hq = _by_kind(base, HQ_KINDS) + [f for f in docs if doc_cls(f) in HQ_DOC_CLASSES and doc_code(f) not in RISK_DOCS]
    risk = _by_kind(base, RISK_KINDS) + [f for f in docs if doc_cls(f) in RISK_DOC_CLASSES or doc_code(f) in RISK_DOCS]
    out = [
        Folder("00_관리자_공통(소유 전행 공통)", None, "관리자", common),
        Folder(f"01_종합기획부(소유 {HQ_TEAM.code} {HQ_TEAM.name})", HQ_TEAM.code, "종기부시험(20269101) 또는 관리자", hq),
        Folder(f"02_신용리스크관리부_{RISK_TEAM.name}(소유 {RISK_TEAM.code})", RISK_TEAM.code, "모형시험(20269201) 또는 관리자", risk),
    ]
    for n, b in enumerate(BRANCHES, start=3):
        out.append(Folder(f"{n:02d}_영업점_{b.code} {b.name}(소유 {b.code})", b.code, "관리자(영업점은 자료 올리기 화면이 없음 — 소유를 그 지점으로 골라 올림)", _tidy_files(branch_files(b))))
    return out


GUIDE = """NAVI 시나리오 자료 (시뮬레이션 · 실제 고객 정보 아님)

0) 시작 상태 — 정의만 있는 빈 플랫폼. 이미 자료가 있으면 서버에서
     docker compose exec api python -m nhdip.cli reset-data          (미리보기)
     docker compose exec api python -m nhdip.cli reset-data --yes    (실제 비우기 · 사용자 · 설정 · 정의는 남음)

1) 조직 — 관리자 [조직 관리]에서 아래 조직이 없으면 추가합니다.
{orgs}
2) 가입 · 승인 — 각 사번으로 가입(비밀번호 아무거나 규칙대로)하고, 관리자 [사용자]에서 승인할 때 업무 소속을 확인합니다.
{accounts}
3) 자료 올리기 — 폴더 번호 순서대로 올립니다(마스터가 먼저). 관리자 [데이터셋·문서]에서 '자료를 둘 팀 · 영업점'을 폴더 이름의 소유로 고르고 올립니다.
   종합기획부 · 신용모형팀 자료는 그 계정이 [자료 올리기]로 올리고 관리자가 [자료 승인]해도 됩니다(소유가 자기 팀으로 정해짐).
   문서(PDF)는 [데이터셋·문서 › 문서]에서 아래 적힌 분류 · 출처로 고릅니다.
   한 번에 올리려면(관리자 계정 · 조직 추가 포함, 가입은 직접):
     docker compose exec -e NHDIP_SAMPLE_UPLOAD=1 api python -m nhdip.sample scenario-upload --base-url http://localhost:8000 --user <관리자 사번>
{folders}
4) 계산 — 다 올리면 워커가 흐름을 차례로 돌립니다(관리자 [실행 현황]에서 wf_hq_goal_review · wf_model_monitoring · wf_inclusive_risk · wf_branch_kpi 성공 확인).

5) 시나리오 확인
   종기부시험   [현황·목표] 여신 현황 · 목표 대비 이탈 → [경영목표 설정] 제안 검토 → 목표 확정(수정 · 신설)
   모형시험     [현황] 모형 모니터링 · 포용금융 → [분석 결과] 보고서 → [수행방안] 진행사업 등록 · '영업점 참고' 켜기
   강남 · 서초 · 역삼시험  [현황] 자기 지점만 · [분석 결과] 우량기업 · 서민금융 가이드(사업부서 수행방안 · 확정 목표를 근거로) · [본부 전파 목표·가이드]
   본부시험     [영업점 업적평가 통합] 세 지점 순위 · 득점률 · 평균
   모두         [AI 어시스턴트] 자기 권한 안의 수치 · 근거로 답변
   목표를 확정하거나 수행방안의 영업점 참고를 켜면 사업부서 · 영업점 흐름이 다시 돌아 의견이 바뀝니다(관리자 [실행 현황]의 원인 '경영목표' · '수행방안 공유').
"""


def write(out_dir: str) -> dict[str, Any]:
    fs = folders()
    manifest: dict[str, Any] = {"region": {"code": REGION_CODE, "name": REGION_NAME}, "orgs": [o.__dict__ for o in NEW_ORGS],
                                "accounts": [{"empNo": e, "name": n, "org": o, "desc": d} for e, n, o, d in ACCOUNTS], "folders": []}
    for fd in fs:
        d = os.path.join(out_dir, fd.name)
        os.makedirs(d, exist_ok=True)
        items = []
        for f in fd.files:
            with open(os.path.join(d, f.name), "wb") as fh:
                fh.write(f.content)
            it: dict[str, Any] = {"name": f.name, "kind": f.kind, "origin": f.origin}
            if f.kind == "dataset":
                it.update({"rows": f.rows, "note": f.note})
            else:
                it.update({k: v for k, v in (f.doc or {}).items() if k in ("docCode", "docClass", "title", "issuer", "publishedAt")})
            items.append(it)
        manifest["folders"].append({"folder": fd.name, "owner": fd.owner, "who": fd.who, "files": items})
    orgs = "\n".join(f"   - {o.code} {o.name} · 유형 팀 · 상위 {o.parent}" for o in NEW_ORGS)
    accounts = "\n".join(f"   - 사번 {e} · 이름 {n} · 소속 {o} ({d})" for e, n, o, d in ACCOUNTS)
    lines = []
    for fd in fs:
        lines.append(f"   - {fd.name} — {len(fd.files)}개 · 올리는 사람: {fd.who}")
        for f in fd.files:
            if f.kind == "document":
                cls = str((f.doc or {}).get("docClass") or "")
                lines.append(f"       문서  {f.name}  → 분류 {DOC_CLASS_KO.get(cls, cls)}({cls}) · 출처 {'외부' if f.origin == 'ext' else '당행'}")
            else:
                lines.append(f"       자료  {f.name}" + (" · 출처 외부" if f.origin == "ext" else ""))
    flist = "\n".join(lines)
    with open(os.path.join(out_dir, "안내.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(GUIDE.format(orgs=orgs, accounts=accounts, folders=flist))
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return {"out": out_dir, "folders": {fd.name: len(fd.files) for fd in fs}}


def upload_http(base_url: str, emp_no: str, password: str, *, client: Any = None) -> dict[str, Any]:
    """관리자 계정으로 조직(신용모형팀) 추가 → 폴더 순서대로 폴더 소유로 업로드. 가입 · 승인은 사람이 한다(비밀번호를 여기서 정하지 않는다).
    같은 파일이 이미 현재 판이면 건너뛴다(다시 실행해도 같은 결과)."""
    from .load import HttpUploader

    up = HttpUploader(base_url, emp_no, password, client=client)
    c = up.c
    rep: dict[str, Any] = {"orgs": [], "uploaded": 0, "skipped": 0, "failed": []}
    for o in NEW_ORGS:
        r = c.post("/admin/orgs", json={"code": o.code, "name": o.name, "unit_type": o.unit_type, "parent_code": o.parent, "sort": o.sort})
        rep["orgs"].append({"code": o.code, "http": r.status_code})
        if r.status_code not in (201, 409):
            rep["failed"].append({"org": o.code, "http": r.status_code, "detail": r.text[:300]})
    have_files, have_docs, _ = up.existing()
    for fd in folders():
        owner = fd.owner or ""
        for f in fd.files:
            if f.kind == "dataset":
                if f.name in have_files:
                    rep["skipped"] += 1
                    continue
                r = c.post("/admin/datasets/auto-upload", data={"origin": f.origin, "data_origin": f.data_origin, "note": f.note or "", "owner_org": owner, "force": "true"}, files={"file": (f.name, f.content)})
                ok = r.status_code == 201 and (r.json() or {}).get("status") == "committed"
            else:
                d = f.doc or {}
                if have_docs.get(d.get("docCode")) == f.name:
                    rep["skipped"] += 1
                    continue
                form = {"origin": f.origin, "doc_class": d["docClass"], "title": d["title"], "doc_code": d["docCode"], "issuer": d.get("issuer") or "", "published_at": d.get("publishedAt") or "",
                        "meta": json.dumps(d.get("meta") or {}, ensure_ascii=False), "owner_org": owner}
                r = c.post("/admin/documents/upload", data=form, files={"file": (f.name, f.content, "application/pdf")})
                ok = r.status_code == 201
            if ok:
                rep["uploaded"] += 1
            else:
                rep["failed"].append({"folder": fd.name, "file": f.name, "http": r.status_code, "detail": r.text[:300]})
    rep["ok"] = not rep["failed"]
    return rep
