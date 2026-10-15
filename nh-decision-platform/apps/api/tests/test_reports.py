"""보고서 변환 동시성 (8.3 에서 발견) — HWPX · HWP 를 동시에 만들어도 모두 성공해야 한다. DB 불필요."""
from concurrent.futures import ThreadPoolExecutor

from nhdip.reports import render
from nhdip.sample.build import business_config


def test_concurrent_hangul_exports():
    # 보고서 틀은 업무 구성 파일의 화면 틀(Phase O)
    report = next(a["payload"] for a in business_config()["artifacts"] if a["key"] == "report.model-monitoring")
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(lambda f: render(report, f), ["hwpx", "hwp", "hwpx", "hwp", "pdf", "hwpx"]))
    assert all(len(b) > 1000 for b in out)
    assert out[0][:2] == b"PK" and out[1][:4] == bytes.fromhex("d0cf11e0") and out[4][:5] == b"%PDF-"
