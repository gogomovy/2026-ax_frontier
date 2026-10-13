"""시연 자료 패키지 도구 (Phase I).

  python -m nhdip.sample build --out sample-data/202608 [--perturb N]      파일로 쓰기(manifest.json 포함)
  python -m nhdip.sample upload --base-url URL --user 사번 [--password-env 변수] [--force] [--perturb N]
                                                                         실제 업로드 API 로 올리기(관리자 로그인)
  python -m nhdip.sample verify --base-url URL --user 사번 [--password-env 변수]
                                                                         엑셀 독립 계산 ↔ 화면 API 수치 대조(어긋나면 종료 코드 1)
  python -m nhdip.sample selftest --user 사번 [--password-env 변수] [--json 파일]
                                                                         현재 DB(정의 시드만)에서 업로드 → 대조 → 교란 검사(하드코딩이 남으면 종료 코드 1)
  python -m nhdip.sample check --dir sample-data/202608                  저장소 사본이 생성기와 같은지(셀 값 · 문서 글)
비밀번호는 환경변수로만 받는다(기본 BOOTSTRAP_ADMIN_PASSWORD).
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _password(args: argparse.Namespace) -> str:
    pw = os.environ.get(args.password_env or "BOOTSTRAP_ADMIN_PASSWORD", "")
    if not pw:
        sys.exit(f"비밀번호 환경변수 {args.password_env or 'BOOTSTRAP_ADMIN_PASSWORD'} 가 비어 있습니다")
    return pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nhdip.sample")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    b.add_argument("--perturb", type=int)
    for name in ("upload", "verify", "selftest"):
        p = sub.add_parser(name)
        if name != "selftest":
            p.add_argument("--base-url", required=True)
        p.add_argument("--user", default=os.environ.get("BOOTSTRAP_ADMIN_EMP_NO", "00000001"))
        p.add_argument("--password-env", default="BOOTSTRAP_ADMIN_PASSWORD")
        if name == "upload":
            p.add_argument("--force", action="store_true")
            p.add_argument("--perturb", type=int)
        if name == "selftest":
            p.add_argument("--json")
    c = sub.add_parser("check")
    c.add_argument("--dir", required=True)
    args = ap.parse_args(argv)

    from .build import build

    if args.cmd == "build":
        pkg = build(perturb_seed=args.perturb)
        paths = pkg.write(args.out)
        print(json.dumps({"out": args.out, "files": len(paths), "variant": pkg.variant}, ensure_ascii=False))
        return 0
    if args.cmd == "upload":
        from .load import upload_http

        rep = upload_http(args.base_url, args.user, _password(args), build(perturb_seed=args.perturb), force=args.force)
        print(json.dumps({k: v for k, v in rep.as_dict().items() if k != "files"}, ensure_ascii=False, indent=1))
        return 0 if rep.ok else 1
    if args.cmd == "verify":
        from .verify import verify_http

        rep = verify_http(args.base_url, args.user, _password(args))
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0 if rep["ok"] else 1
    if args.cmd == "selftest":
        from .verify import selftest, to_json

        rep = selftest(args.user, _password(args))
        text = to_json(rep)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                fh.write(text)
        print(text[:20000])
        return 0 if rep["ok"] else 1
    if args.cmd == "check":
        from .check import compare_dir

        diffs = compare_dir(build(), args.dir)
        print(json.dumps({"dir": args.dir, "ok": not diffs, "diffs": diffs[:50]}, ensure_ascii=False, indent=1))
        return 0 if not diffs else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
