"""보고서 변환 동시성 (8.3 에서 발견) — HWPX · HWP 를 동시에 만들어도 모두 성공해야 한다. DB 불필요."""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from nhdip.reports import render

REPORT = os.path.join(os.path.dirname(__file__), "..", "src", "nhdip", "seed", "screens", "report.model-monitoring.json")


def test_concurrent_hangul_exports():
    report = json.load(open(REPORT, encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(lambda f: render(report, f), ["hwpx", "hwp", "hwpx", "hwp", "pdf", "hwpx"]))
    assert all(len(b) > 1000 for b in out)
    assert out[0][:2] == b"PK" and out[1][:4] == bytes.fromhex("d0cf11e0") and out[4][:5] == b"%PDF-"
