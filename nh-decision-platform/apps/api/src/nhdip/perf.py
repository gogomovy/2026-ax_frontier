"""성능 측정 (작업 8.3 · NFR) — `python -m nhdip.perf [--base URL] [--n 30] [--c 4] [--json 파일]`.

기동 중인 스택에 관리자 계정으로 로그인해 주요 API 를 동시 요청으로 호출하고 p50 · p95 · 최대 · 오류율을 잰다.
기준치(budgets)는 `perf_budgets.json` — 넘으면 종료 코드 1. 서버 쪽 DB 구간은 관리자 [요청 추적]에서 같은 추적 ID 로 본다.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BUDGETS = os.path.join(os.path.dirname(__file__), "perf_budgets.json")


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[i]


def measure(base: str, emp: str, pw: str, n: int, conc: int, budgets: dict) -> dict:
    with httpx.Client(base_url=base, timeout=60) as c:
        r = c.post("/auth/login", json={"emp_no": emp, "password": pw})
        r.raise_for_status()
        cookies = dict(c.cookies)
    results = {}
    for sc in budgets["scenarios"]:
        times: list[float] = []
        errors = 0

        def one(_: int) -> tuple[float, bool]:
            with httpx.Client(base_url=base, timeout=60, cookies=cookies) as cl:
                t0 = time.perf_counter()
                resp = cl.request(sc.get("method", "GET"), sc["path"], json=sc.get("json"))
                return (time.perf_counter() - t0) * 1000, resp.status_code < 400

        count = int(sc.get("n", n))
        with ThreadPoolExecutor(max_workers=int(sc.get("c", conc))) as ex:
            for ms, ok in ex.map(one, range(count)):
                times.append(ms)
                errors += 0 if ok else 1
        p95 = _pct(times, 95)
        budget = sc.get("p95_ms")
        results[sc["name"]] = {
            "path": sc["path"], "n": count, "p50_ms": round(_pct(times, 50), 1), "p95_ms": round(p95, 1), "max_ms": round(max(times), 1),
            "mean_ms": round(statistics.fmean(times), 1), "error_rate": round(errors / count, 4), "budget_p95_ms": budget,
            "ok": (budget is None or p95 <= budget) and errors / count <= float(budgets.get("max_error_rate", 0.0)),
        }
    return {"base": base, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "results": results, "passed": all(v["ok"] for v in results.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nhdip.perf")
    ap.add_argument("--base", default=os.environ.get("PERF_BASE", "http://web:3000/backend"))
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--c", type=int, default=4)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    with open(BUDGETS, encoding="utf-8") as fh:
        budgets = json.load(fh)
    rep = measure(a.base, os.environ.get("BOOTSTRAP_ADMIN_EMP_NO", "00000001"), os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", ""), a.n, a.c, budgets)
    print(f"{'시나리오':24s} {'p50':>8s} {'p95':>8s} {'max':>8s} {'기준 p95':>9s} {'오류':>6s}")
    for name, r in rep["results"].items():
        print(f"{name:24s} {r['p50_ms']:8.1f} {r['p95_ms']:8.1f} {r['max_ms']:8.1f} {str(r['budget_p95_ms']):>9s} {r['error_rate']:6.1%} {'OK' if r['ok'] else 'NG'}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    print("PASS" if rep["passed"] else "FAIL")
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
