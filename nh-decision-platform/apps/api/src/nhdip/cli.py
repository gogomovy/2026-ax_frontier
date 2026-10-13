"""운영 CLI.

  python -m nhdip.cli seed [--with-precompute]     기본 설정 + 목데이터 시드 (멱등)
  python -m nhdip.cli admin-password <사번>         비밀번호 재설정(표준입력) + 잠금 해제
  python -m nhdip.cli run <workflow_code>           워크플로우 즉시 실행(동기)
  python -m nhdip.cli db-app-role                  API 전용 DB 계정 생성 · 권한 부여 (APP_DB_PASSWORD, 소유자 계정으로 실행)
  python -m nhdip.cli preflight                    운영 준비 점검 (fail 이 있으면 종료 코드 1, --json 이면 JSON)
  python -m nhdip.cli record-backup <폴더> <바이트>  백업 기록 남기기 (make backup 이 호출 — 운영 준비 점검의 '백업' 항목)
  python -m nhdip.cli wait-idle [--timeout 300]    미처리 이벤트 · 대기 · 실행 중 작업이 없을 때까지 대기 (CI · 기동 직후 점검)
  python -m nhdip.cli kb-hnsw --dim N              질문하기 분석 결과 색인에 부분 HNSW 인덱스 생성 + 검색 설정(knowledge.search.hnsw_dim) 반영 (임베딩 모델 확정 후)
  python -m nhdip.cli kb-calibrate [--apply]       현재 임베딩 모델의 코사인 거리 임계값 추천(엉뚱한 질문 vs 제목 질문 분포), --apply 면 확신할 때만 반영
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
    sub.add_parser("db-app-role")
    ap_pf = sub.add_parser("preflight")
    ap_pf.add_argument("--json", action="store_true")
    ap_rb = sub.add_parser("record-backup")
    ap_rb.add_argument("folder")
    ap_rb.add_argument("size", type=int, nargs="?", default=0)
    ap_wait = sub.add_parser("wait-idle")
    ap_wait.add_argument("--timeout", type=int, default=300)
    ap_wait.add_argument("--settle", type=int, default=5, help="연속으로 비어 있어야 하는 초")
    ap_wait.add_argument("--strict", action="store_true", help="시간 초과면 종료 코드 1")
    ap_hn = sub.add_parser("kb-hnsw")
    ap_hn.add_argument("--dim", type=int, required=True, help="임베딩 차원(모델 확정 후, 2~2000)")
    ap_cal = sub.add_parser("kb-calibrate")
    ap_cal.add_argument("--apply", action="store_true", help="확신할 수 있는 추천값을 검색 설정(max_cosine_distance)에 반영")
    args = ap.parse_args(argv)

    if args.cmd == "kb-calibrate":
        from nhdip.knowledge.calibration import apply_calibration, calibrate
        from nhdip.llm import LlmUnavailable

        with SessionLocal() as s:
            try:
                rep = calibrate(s)
                if args.apply:
                    apply_calibration(s, rep, "cli")
                    s.commit()
                    rep["applied"] = True
            except (LlmUnavailable, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return 0

    if args.cmd == "kb-hnsw":
        from nhdip.knowledge.maintenance import ensure_hnsw

        try:
            with SessionLocal() as s:
                print(json.dumps(ensure_hnsw(s, args.dim), ensure_ascii=False))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
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
    if args.cmd == "preflight":
        from nhdip.preflight import run_checks

        with SessionLocal() as s:
            rep = run_checks(s)
        if args.json:
            print(json.dumps(rep, ensure_ascii=False, indent=1))
        else:
            mark = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}
            for it in rep["items"]:
                print(f"{mark[it['level']]}  {it['label']:<14} {it['message']}")
                if it["fix"] and it["level"] != "ok":
                    print(f"      → {it['fix']}")
            c = rep["counts"]
            print(f"\n정상 {c['ok']} · 확인 {c['warn']} · 위험 {c['fail']} — {'운영 가능' if rep['ready'] else '위험 항목을 먼저 고치세요'}")
        return 0 if rep["ready"] else 1
    if args.cmd == "record-backup":
        from nhdip.events import audit

        with SessionLocal() as s:
            audit(s, "ops", "ops.backup", "backup", args.folder[:200], {"bytes": args.size}, None)
            s.commit()
        print("ok")
        return 0
    if args.cmd == "db-app-role":
        from sqlalchemy import create_engine

        from nhdip.config import get_settings
        from nhdip.dbrole import ensure_app_role

        st = get_settings()
        if not st.app_db_password:
            print("APP_DB_PASSWORD 가 비어 있어 건너뜀 (api 는 소유자 계정으로 접속)")
            return 0
        eng = create_engine(st.database_url, future=True)  # 소유자 계정
        try:
            print(json.dumps({"role": st.app_db_user, "steps": ensure_app_role(eng, st.app_db_user, st.app_db_password)}, ensure_ascii=False))
        finally:
            eng.dispose()
        return 0
    if args.cmd == "wait-idle":
        import time

        from sqlalchemy import func, select

        from nhdip.models import Job, OutboxEvent

        t0, quiet_since = time.monotonic(), None
        while time.monotonic() - t0 < args.timeout:
            with SessionLocal() as s:
                ev = s.execute(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dispatched_at.is_(None))).scalar() or 0
                jobs = s.execute(select(func.count()).select_from(Job).where(Job.status.in_(["queued", "running"]))).scalar() or 0
            if ev == 0 and jobs == 0:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= args.settle:
                    print(json.dumps({"idle": True, "waited_sec": round(time.monotonic() - t0)}))
                    return 0
            else:
                quiet_since = None
            time.sleep(2)
        print(json.dumps({"idle": False, "waited_sec": args.timeout, "events": ev, "jobs": jobs}))
        return 1 if args.strict else 0
    if args.cmd == "run":
        from nhdip.workflow.engine import run_workflow

        with SessionLocal() as s:
            run = run_workflow(s, args.workflow, [{"type": "cli"}])
            print(json.dumps({"run": run.id, "status": run.status, "summary": run.summary, "error": run.error}, ensure_ascii=False, default=str))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
