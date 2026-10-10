"""운영 CLI.

  python -m nhdip.cli seed [--with-precompute]     기본 설정 + 목데이터 시드 (멱등)
  python -m nhdip.cli admin-password <사번>         비밀번호 재설정(표준입력) + 잠금 해제
  python -m nhdip.cli run <workflow_code>           워크플로우 즉시 실행(동기)
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from nhdip.db import SessionLocal


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nhdip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed")
    sp.add_argument("--with-precompute", action="store_true")
    ap_pw = sub.add_parser("admin-password")
    ap_pw.add_argument("emp_no")
    ap_run = sub.add_parser("run")
    ap_run.add_argument("workflow")
    args = ap.parse_args(argv)

    if args.cmd == "seed":
        from nhdip.seed.run import run_seed

        with SessionLocal() as s:
            print(json.dumps(run_seed(s, with_precompute=args.with_precompute), ensure_ascii=False))
        return 0
    if args.cmd == "admin-password":
        from nhdip.models import AppUser
        from nhdip.security import hash_password, password_policy_error

        pw = sys.stdin.readline().strip() if not sys.stdin.isatty() else getpass.getpass("새 비밀번호: ")
        err = password_policy_error(pw)
        if err:
            print(err, file=sys.stderr)
            return 2
        with SessionLocal() as s:
            u = s.get(AppUser, args.emp_no)
            if not u:
                print("사용자 없음", file=sys.stderr)
                return 1
            u.password_hash = hash_password(pw)
            u.failed_count = 0
            if u.status == "locked":
                u.status = "active"
            s.commit()
        print("ok")
        return 0
    if args.cmd == "run":
        from nhdip.workflow.engine import run_workflow

        with SessionLocal() as s:
            run = run_workflow(s, args.workflow, [{"type": "cli"}])
            print(json.dumps({"run": run.id, "status": run.status, "summary": run.summary, "error": run.error}, ensure_ascii=False, default=str))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
