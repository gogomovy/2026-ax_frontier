"""시연 자료 패키지 올리기 (Phase I · Q137 · Phase O) — 실제 업로드 경로만 쓴다. 미리 정한 정의 없음.

- 업무 구성 파일 → `POST /admin/business-config` (같은 이름 · 같은 내용이 이미 반영돼 있으면 건너뜀)
- 자료 → `POST /admin/datasets/auto-upload` (맞는 정의가 있으면 그 자료의 새 버전, 없으면 파일에서 정의를 만들어 첫 버전)
- 문서 → `POST /admin/documents/upload`
- `load_local`: 같은 함수(bizconfig.apply · auto_target · infer · ingest)로 HTTP 없이 (시험 전용 — 플랫폼 기동 · CLI 는 쓰지 않음, M.20)
- 이미 같은 파일 이름으로 확정된 버전(문서는 같은 문서 코드 · 같은 파일)이 있으면 건너뛴다(`force=True` 면 새 버전으로 — 교란 검사)
- 응답 상태가 committed 가 아니면 실패로 모은다(품질 경고는 허용). `codes` = 시나리오 자료 구분 → 플랫폼이 만든 데이터셋 코드
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .build import Package, SampleFile


@dataclass
class LoadReport:
    uploaded: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    codes: dict[str, str] = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.failed

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "uploaded": len(self.uploaded), "skipped": len(self.skipped), "failed": self.failed, "seconds": round(self.seconds, 1),
                "codes": self.codes, "files": self.uploaded}


# ═════════════════════════ 로컬(같은 적재 함수) ═════════════════════════
def load_local(session: Any, pkg: Package, *, actor: str = "sample", force: bool = False) -> LoadReport:
    from sqlalchemy import select

    from nhdip.api.db_uploads import auto_target
    from nhdip.bizconfig.apply import apply, current
    from nhdip.bizconfig.bundle import read_bundle
    from nhdip.data.datasets import ingest_file
    from nhdip.data.documents import clean_doc_meta, ingest_document
    from nhdip.data.filecheck import check_upload
    from nhdip.data.infer import infer_definition
    from nhdip.models import Dataset, Setting, source

    rep, t0 = LoadReport(), time.monotonic()
    pol_row = session.get(Setting, "upload.policy")
    pol = pol_row.value if pol_row else None
    for f in pkg.files:
        try:
            if f.kind == "config":
                cur = current(session, read_bundle(f.name, f.content)["name"])
                if cur is not None and not force and cur.sha256 == hashlib.sha256(f.content).hexdigest():
                    rep.skipped.append(f.name)
                    continue
                cfg = apply(session, read_bundle(f.name, f.content), actor=actor, file_name=f.name, content=f.content)
                session.commit()
                rep.uploaded.append({"file": f.name, "config": cfg.name, "version": cfg.version, "status": "committed"})
            elif f.kind == "dataset":
                name = check_upload(f.name, f.content, "dataset", pol)
                ds, _ = auto_target(session, name, f.content, include_common=True)
                if ds is not None:
                    t = source(ds.origin)
                    if not force and session.execute(select(t.version.id).where(t.version.dataset_code == ds.code, t.version.file_name == f.name, t.version.status == "committed").limit(1)).first():
                        rep.skipped.append(f.name)
                        rep.codes.setdefault(f.dataset or "", ds.code)
                        continue
                else:
                    out = infer_definition(f.content, name, origin=f.origin)
                    base, n = out["code"], 2
                    while session.get(Dataset, out["code"]) is not None:
                        out["code"], n = f"{base}_{n}"[:60], n + 1
                    keys = ("code", "name", "origin", "kind", "description", "file_pattern", "refresh_cycle", "columns", "key_columns", "as_of_column", "mapping", "quality_rules", "parser")
                    ds = Dataset(**{k: out[k] for k in keys if out.get(k) is not None})
                    session.add(ds)
                    session.flush()
                v = ingest_file(session, ds, name, f.content, data_origin=f.data_origin, actor=actor, note=f.note, force=force)
                session.commit()
                rep.codes.setdefault(f.dataset or "", ds.code)
                item = {"file": f.name, "dataset": ds.code, "kind": f.dataset, "status": v.status, "version": v.version, "rows": v.row_count, "quality": v.quality.get("status")}
                (rep.uploaded if v.status == "committed" else rep.failed).append(item)
            else:
                d = f.doc or {}
                t = source(f.origin)
                cur_doc = session.execute(select(t.document).where(t.document.doc_code == d["docCode"], t.document.is_current)).scalars().first()
                if cur_doc is not None and not force and cur_doc.file_sha256 == f.sha256:
                    rep.skipped.append(f.name)
                    continue
                name = check_upload(f.name, f.content, "document", pol)
                doc = ingest_document(session, origin=f.origin, doc_code=d["docCode"], title=d["title"], doc_class=d["docClass"], filename=name, content=f.content,
                                      issuer=d.get("issuer"), published_at=d.get("publishedAt"), meta=clean_doc_meta(d.get("meta"), f.origin), actor=actor)
                session.commit()
                rep.uploaded.append({"file": f.name, "docCode": doc.doc_code, "version": doc.version, "status": "committed"})
        except Exception as exc:  # noqa: BLE001 — 파일 하나의 실패를 모아 보고
            session.rollback()
            rep.failed.append({"file": f.name, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    rep.seconds = time.monotonic() - t0
    return rep


# ═════════════════════════ HTTP(실제 업로드 API) ═════════════════════════
class HttpUploader:
    def __init__(self, base_url: str, emp_no: str, password: str, *, timeout: float = 180.0, client: Any = None):
        import httpx

        self.base = base_url.rstrip("/")
        self.c = client or httpx.Client(base_url=self.base, timeout=timeout)
        r = self.c.post("/auth/login", json={"emp_no": emp_no, "password": password})
        if r.status_code != 200:
            raise RuntimeError(f"관리자 로그인 실패 {r.status_code}: {r.text[:200]}")
        # 보안 쿠키(Secure)라도 내부 http 주소로 보내도록 쿠키를 직접 싣는다(서버 간 호출 · Origin 없음)
        cookies = {k: v for k, v in r.cookies.items()} or {k: v for k, v in self.c.cookies.items()}
        if cookies:
            self.c.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())

    def existing(self) -> tuple[dict[str, str], dict[str, str | None], dict[str, str]]:
        """(올라온 파일 이름 → 데이터셋 코드, 현재 문서 코드 → 파일 이름, 활성 구성 이름 → 파일 sha256)."""
        ds = self.c.get("/admin/datasets")
        ds.raise_for_status()
        files = {v["fileName"]: d["code"] for d in ds.json() for v in d.get("versions", []) if v.get("status") == "committed" and v.get("fileName")}
        docs = self.c.get("/admin/documents")
        docs.raise_for_status()
        cur = {d["docCode"]: d.get("fileName") for d in docs.json() if d.get("isCurrent")}
        cfg = self.c.get("/admin/business-config")
        cfg.raise_for_status()
        cfgs = {c["name"]: c.get("sha256") or "" for c in cfg.json().get("items") or []}
        return files, cur, cfgs

    def config(self, f: SampleFile) -> dict[str, Any]:
        r = self.c.post("/admin/business-config", files={"file": (f.name, f.content)})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:300]}
        return {"http": r.status_code, **body}

    def dataset(self, f: SampleFile, force: bool = False) -> dict[str, Any]:
        r = self.c.post("/admin/datasets/auto-upload", data={"origin": f.origin, "data_origin": f.data_origin, "note": f.note or "", "force": "true" if force else "false"}, files={"file": (f.name, f.content)})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:300]}
        return {"http": r.status_code, **body}

    def document(self, f: SampleFile) -> dict[str, Any]:
        d = f.doc or {}
        form = {"origin": f.origin, "doc_class": d["docClass"], "title": d["title"], "doc_code": d["docCode"], "issuer": d.get("issuer") or "", "published_at": d.get("publishedAt") or "",
                "meta": json.dumps(d.get("meta") or {}, ensure_ascii=False)}
        r = self.c.post("/admin/documents/upload", data=form, files={"file": (f.name, f.content, "application/pdf")})
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:300]}
        return {"http": r.status_code, **body}


def upload_http(base_url: str, emp_no: str, password: str, pkg: Package, *, force: bool = False, client: Any = None, config: bool = True) -> LoadReport:
    rep, t0 = LoadReport(), time.monotonic()
    up = HttpUploader(base_url, emp_no, password, client=client)
    have_files, have_docs, have_cfg = up.existing()
    for f in pkg.files:
        if f.kind == "config":
            if not config:
                continue
            from nhdip.bizconfig.bundle import read_bundle

            if have_cfg.get(read_bundle(f.name, f.content)["name"]) == hashlib.sha256(f.content).hexdigest() and not force:
                rep.skipped.append(f.name)
                continue
            res = up.config(f)
            if res["http"] == 201:
                rep.uploaded.append({"file": f.name, "config": res.get("name"), "version": res.get("version"), "status": "committed"})
            else:
                rep.failed.append({"file": f.name, "http": res["http"], "detail": str(res.get("detail"))[:600]})
        elif f.kind == "dataset":
            if f.name in have_files and not force:
                rep.skipped.append(f.name)
                rep.codes.setdefault(f.dataset or "", have_files[f.name])
                continue
            res = up.dataset(f, force=force)
            item = {"file": f.name, "dataset": res.get("dataset"), "kind": f.dataset, "status": res.get("status"), "version": res.get("version"), "rows": res.get("rows"),
                    "quality": (res.get("quality") or {}).get("status")}
            if res["http"] == 201 and res.get("status") == "committed":
                rep.uploaded.append(item)
                rep.codes.setdefault(f.dataset or "", res.get("dataset"))
            else:
                rep.failed.append({**item, "http": res["http"], "detail": str(res.get("detail") or res.get("quality") or "")[:300]})
        else:
            d = f.doc or {}
            if have_docs.get(d.get("docCode")) == f.name and not force:
                rep.skipped.append(f.name)
                continue
            res = up.document(f)
            if res["http"] == 201:
                rep.uploaded.append({"file": f.name, "docCode": res.get("docCode"), "version": res.get("version"), "status": "committed"})
            else:
                rep.failed.append({"file": f.name, "http": res["http"], "detail": str(res.get("detail"))[:300]})
    rep.seconds = time.monotonic() - t0
    return rep
