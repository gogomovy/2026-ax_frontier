"""업로드 파일 보안 검사 (작업 8.4.4 · ING-02) — 확장자 허용 목록 · 매직 바이트 · 압축 폭탄 · 매크로 · PDF 능동 콘텐츠 · DRM.

검사는 파싱 전에 수행한다. 실패는 사용자에게 고칠 수 있는 이유로 돌려준다(422).
외부 백신(ClamAV 등)은 배포 환경변수 `UPLOAD_AV_COMMAND` 가 있을 때만 호출한다(기본 끔 — Docker 구성에 백신 없음).
명령은 관리자 화면 설정이 아니라 배포 시점 환경변수로만 받는다(화면에서 임의 명령 실행 방지).
"""
from __future__ import annotations

import io
import os
import re
import shlex
import subprocess
import tempfile
import zipfile
from typing import Any

ALLOWED = {
    # .md — DRM 엑셀을 마크다운 표로 바꿔 올리는 경우(Phase Q · MD-01). 텍스트 검사(이진 데이터 · 인코딩)를 그대로 받는다
    "dataset": {".csv", ".tsv", ".xlsx", ".json", ".md"},
    # 조직 · 인사 .dat (Phase R) — '|' 구분 텍스트, EUC-KR 도 받는다
    "hr_sync": {".dat", ".txt"},
    "document": {".pdf", ".hwpx", ".hwp", ".txt", ".md", ".html"},
    "contract": {".xlsx"},
}
DEFAULTS: dict[str, Any] = {
    "max_mb": 50,
    "zip_max_uncompressed_mb": 300,
    "zip_max_ratio": 150,
    "zip_max_entries": 5000,
    "block_pdf_active": True,
    "av_timeout_sec": 60,
}
_PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)\b")
_NAME_BAD = re.compile(r"[\x00-\x1f\x7f/\\]")


class UploadRejected(ValueError):
    pass


def safe_name(filename: str | None) -> str:
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not name or name in (".", ".."):
        raise UploadRejected("파일 이름이 없습니다")
    if _NAME_BAD.search(name) or len(name) > 200:
        raise UploadRejected("파일 이름에 쓸 수 없는 문자가 있거나 200자를 넘습니다")
    return name


def _check_zip(content: bytes, cfg: dict[str, Any], kind: str) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise UploadRejected("xlsx 파일 구조가 올바르지 않습니다(손상되었거나 다른 형식)") from exc
    infos = zf.infolist()
    if len(infos) > int(cfg["zip_max_entries"]):
        raise UploadRejected("압축 항목 수가 너무 많습니다")
    total = sum(i.file_size for i in infos)
    packed = sum(i.compress_size for i in infos) or 1
    if total > int(cfg["zip_max_uncompressed_mb"]) * 1024 * 1024 or total / packed > float(cfg["zip_max_ratio"]):
        raise UploadRejected("압축 해제 크기 · 비율이 허용 범위를 넘습니다(압축 폭탄 의심)")
    names = {i.filename for i in infos}
    if any(n.startswith("/") or ".." in n.split("/") for n in names):
        raise UploadRejected("압축 내부 경로가 올바르지 않습니다")
    if kind == "hwpx" and "mimetype" not in names:
        raise UploadRejected("한글(HWPX) 파일 구조가 아닙니다")
    if kind == "xlsx":
        if "[Content_Types].xml" not in names or not any(n.startswith("xl/") for n in names):
            raise UploadRejected("엑셀(xlsx) 파일이 아닙니다")
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise UploadRejected("매크로가 포함된 엑셀은 올릴 수 없습니다(매크로 제거 후 xlsx 로 저장)")
        if any(n.lower().startswith("xl/externallinks/") for n in names):
            raise UploadRejected("외부 연결(External Link)이 포함된 엑셀은 올릴 수 없습니다")


def _check_text(content: bytes, allow_cp949: bool = False) -> None:
    if b"\x00" in content[:65536]:
        raise UploadRejected("텍스트 파일에 이진 데이터가 섞여 있습니다")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        if allow_cp949:
            try:
                content.decode("cp949")
                return
            except UnicodeDecodeError:
                pass
        raise UploadRejected("텍스트 파일은 UTF-8 로 저장해 주세요" + (" (또는 CP949)" if allow_cp949 else "")) from exc


def _antivirus(content: bytes, cfg: dict[str, Any]) -> None:
    cmd = os.environ.get("UPLOAD_AV_COMMAND", "").strip()
    if not cmd:
        return
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(content)
        path = fh.name
    try:
        args = shlex.split(cmd.replace("{path}", path)) if "{path}" in cmd else [*shlex.split(cmd), path]
        r = subprocess.run(args, capture_output=True, timeout=int(cfg["av_timeout_sec"]), check=False)  # noqa: S603 — 배포 환경변수 명령
        if r.returncode != 0:
            raise UploadRejected("백신 검사에서 차단되었습니다")
    except subprocess.TimeoutExpired as exc:
        raise UploadRejected("백신 검사 시간이 초과되었습니다") from exc
    except (OSError, ValueError) as exc:
        # 명령이 없거나 실행할 수 없음(오타 · 미설치 · 따옴표 오류) — 검사 없이 통과시키지 않고(fail-closed) 서버 오류(500) 대신 거절로 알린다
        raise UploadRejected("백신 검사 명령을 실행할 수 없어 업로드를 받지 못했습니다 — 관리자에게 알려 주세요(UPLOAD_AV_COMMAND)") from exc
    finally:
        os.unlink(path)


def check_upload(filename: str | None, content: bytes, purpose: str, cfg: dict[str, Any] | None = None) -> str:
    """검사 통과 시 안전한 파일 이름을 돌려준다."""
    c = {**DEFAULTS, **(cfg or {})}
    name = safe_name(filename)
    ext = os.path.splitext(name)[1].lower()
    allowed = ALLOWED.get(purpose, set())
    if ext not in allowed:
        raise UploadRejected(f"허용 형식: {' · '.join(sorted(allowed))}")
    if len(content) > int(c["max_mb"]) * 1024 * 1024:
        raise UploadRejected(f"파일이 너무 큽니다({c['max_mb']}MB 이하)")
    if not content:
        raise UploadRejected("빈 파일입니다")
    if content[:16].find(b"DRMONE") >= 0 or b"Fasoo DRM" in content[:200]:
        raise UploadRejected("DRM 으로 암호화된 파일입니다 — 해제본을 올려 주세요")
    if ext == ".xlsx":
        if not content.startswith(b"PK\x03\x04"):
            if content.startswith(b"\xd0\xcf\x11\xe0"):
                raise UploadRejected("암호가 걸렸거나 예전 형식(xls)인 엑셀입니다 — 암호 해제 후 xlsx 로 저장해 주세요")
            raise UploadRejected("엑셀(xlsx) 파일이 아닙니다")
        _check_zip(content, c, "xlsx")
    elif ext == ".hwpx":
        if not content.startswith(b"PK\x03\x04"):
            raise UploadRejected("한글(HWPX) 파일이 아닙니다")
        _check_zip(content, c, "hwpx")
    elif ext == ".hwp":
        if not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise UploadRejected("한글(HWP 5.0) 파일이 아닙니다")
    elif ext == ".pdf":
        if not content.lstrip()[:5] == b"%PDF-":
            raise UploadRejected("PDF 파일이 아닙니다")
        if c["block_pdf_active"] and _PDF_ACTIVE.search(content):
            raise UploadRejected("스크립트 · 실행 동작 · 첨부 파일이 포함된 PDF 는 올릴 수 없습니다(인쇄 → PDF 로 다시 저장)")
    else:
        # 마크다운은 내부망 변환기 기본값(CP949)도 받는다 — 읽을 때 UTF-8 → CP949 순 (data/mdtable.decode)
        _check_text(content, allow_cp949=ext == ".md" or purpose == "hr_sync")
    _antivirus(content, c)
    return name
