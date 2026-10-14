"""업로드 보안 검사 (작업 8.4.4) — 악성 · 위장 · 압축 폭탄 · 매크로 · DRM · 경로 조작. DB 불필요."""
import io
import shutil
import zipfile

import pytest

from nhdip.data.filecheck import UploadRejected, check_upload, safe_name


def _xlsx(extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


def test_valid_files_pass():
    assert check_upload("a.csv", "ym,v\n202608,1\n".encode(), "dataset") == "a.csv"
    assert check_upload("정의서.xlsx", _xlsx(), "contract") == "정의서.xlsx"
    assert check_upload("r.pdf", b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n%%EOF", "document") == "r.pdf"


@pytest.mark.parametrize(
    "name,content,purpose,msg",
    [
        ("x.exe", b"MZ", "dataset", "허용 형식"),
        ("x.xlsm", _xlsx(), "contract", "허용 형식"),
        ("fake.xlsx", b"not a zip", "dataset", "엑셀"),
        ("old.xlsx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 32, "dataset", "암호"),
        ("macro.xlsx", _xlsx({"xl/vbaProject.bin": b"\0" * 10}), "dataset", "매크로"),
        ("link.xlsx", _xlsx({"xl/externalLinks/externalLink1.xml": "<x/>"}), "dataset", "외부 연결"),
        ("fake.pdf", b"<html>", "document", "PDF 파일이 아닙니다"),
        ("js.pdf", b"%PDF-1.4\n<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>", "document", "스크립트"),
        ("drm.xlsx", b"\x9b DRMONE  This Document is encrypted and protected by Fasoo DRM", "dataset", "DRM"),
        ("bin.csv", b"a,b\n\x00\x01", "dataset", "이진"),
        ("euc.csv", "가,나".encode("euc-kr"), "dataset", "UTF-8"),
        ("empty.csv", b"", "dataset", "빈 파일"),
    ],
)
def test_rejected(name, content, purpose, msg):
    with pytest.raises(UploadRejected, match=msg):
        check_upload(name, content, purpose)


def test_zip_bomb_and_size_limits():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/sheet.xml", b"0" * (20 * 1024 * 1024))  # 20MB → 수십 KB (비율 초과)
    with pytest.raises(UploadRejected, match="압축 폭탄"):
        check_upload("bomb.xlsx", buf.getvalue(), "dataset")
    with pytest.raises(UploadRejected, match="너무 큽니다"):
        check_upload("big.csv", b"a\n" * 600_000, "dataset", {"max_mb": 1})


def test_pdf_active_content_can_be_allowed_by_policy():
    pdf = b"%PDF-1.4\n<< /JavaScript 1 0 R >>"
    assert check_upload("ok.pdf", pdf, "document", {"block_pdf_active": False}) == "ok.pdf"


@pytest.mark.parametrize("name", ["", "..", "a\x00.csv", "a" * 201 + ".csv"])
def test_bad_names(name):
    with pytest.raises(UploadRejected):
        safe_name(name)


def test_path_components_are_stripped():
    assert safe_name("../../etc/passwd.csv") == "passwd.csv"
    assert safe_name("C:\\temp\\x.csv") == "x.csv"


@pytest.mark.skipif(shutil.which("false") is None or shutil.which("true") is None, reason="POSIX 명령 false · true 가 없는 환경(Windows)")
def test_antivirus_hook(monkeypatch):
    monkeypatch.setenv("UPLOAD_AV_COMMAND", "false")
    with pytest.raises(UploadRejected, match="백신"):
        check_upload("a.csv", b"a\n1\n", "dataset")
    monkeypatch.setenv("UPLOAD_AV_COMMAND", "true {path}")
    assert check_upload("a.csv", b"a\n1\n", "dataset") == "a.csv"


def test_antivirus_command_that_cannot_run_rejects_instead_of_crashing(monkeypatch):
    """백신 명령이 없거나 실행할 수 없으면 검사 없이 통과시키지도, 서버 오류(500)를 내지도 않고 거절한다 — 어느 OS 에서나."""
    monkeypatch.setenv("UPLOAD_AV_COMMAND", "nhdip-no-such-antivirus-binary {path}")
    with pytest.raises(UploadRejected, match="백신 검사 명령을 실행할 수 없"):
        check_upload("a.csv", b"a\n1\n", "dataset")
    monkeypatch.setenv("UPLOAD_AV_COMMAND", 'unterminated "quote {path}')  # 따옴표 오류(shlex ValueError)
    with pytest.raises(UploadRejected, match="백신"):
        check_upload("a.csv", b"a\n1\n", "dataset")
