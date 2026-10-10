"""`python -m nhdip.evals [--json 파일] [--publish]` — 골든셋 평가. 기준 미달이면 종료 코드 1."""
from __future__ import annotations

import argparse
import json
import sys

from nhdip.db import SessionLocal

from . import run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nhdip.evals")
    ap.add_argument("--json", help="결과 JSON 저장 경로")
    ap.add_argument("--publish", action="store_true", help="관리자 화면용 산출물(eval.golden)로 게시")
    args = ap.parse_args(argv)
    with SessionLocal() as s:
        rep = run(s)
        if args.publish:
            from nhdip.views.store import publish

            publish(s, "eval.golden", rep, produced_by="eval-cli")
            s.commit()
    for name, c in rep["categories"].items():
        mark = "OK " if c["ok"] else "NG "
        print(f"{mark}{name:10s} {c['passed']}/{c['total']} ({c['rate']:.0%}, 기준 {c['threshold']:.0%})")
        for f in c["failures"]:
            print(f"     ✗ {f['case']} — {json.dumps({k: v for k, v in f.items() if k not in ('case', 'passed')}, ensure_ascii=False)[:200]}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    print("PASS" if rep["passed"] else "FAIL")
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
