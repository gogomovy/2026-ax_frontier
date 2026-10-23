"""운영 CLI.

  python -m nhdip.cli seed [--with-precompute]     정의 시드 — 사용자 · 조직 · 설정 · 규칙 · 데이터셋 정의 · 지표 · 워크플로 · 값 없는 화면 틀 (멱등, 업무 자료는 넣지 않음)
  python -m nhdip.cli reset-data [--yes] [--force]  업무 자료 비우기 — 올린 자료 · 계산 결과 · 화면 산출물 · 색인 · 그래프 · 실행 기록을 지우고 정의만 남김.
                                                   인자 없으면 미리보기(지울 행 수), --yes 로 실행. 사용자 · 설정 · 정의 · 감사 기록은 남는다 (M.19 · Q203)
  python -m nhdip.cli admin-password <사번>         비밀번호 재설정(표준입력) + 잠금 해제
  python -m nhdip.cli run <workflow_code>           워크플로우 즉시 실행(동기)
  python -m nhdip.cli db-app-role                  API 전용 DB 계정 생성 · 권한 부여 (APP_DB_PASSWORD, 소유자 계정으로 실행)
  python -m nhdip.cli preflight                    운영 준비 점검 (fail 이 있으면 종료 코드 1, --json 이면 JSON)
  python -m nhdip.cli record-backup <폴더> <바이트>  백업 기록 남기기 (make backup 이 호출 — 운영 준비 점검의 '백업' 항목)
  python -m nhdip.cli wait-idle [--timeout 300]    미처리 이벤트 · 대기 · 실행 중 작업이 없을 때까지 대기 (CI · 기동 직후 점검)
  python -m nhdip.cli kb-hnsw --dim N              질문하기 분석 결과 색인에 부분 HNSW 인덱스 생성 + 검색 설정(knowledge.search.hnsw_dim) 반영 (임베딩 모델 확정 후)
  python -m nhdip.cli kb-calibrate [--apply]       현재 임베딩 모델의 코사인 거리 임계값 추천(엉뚱한 질문 vs 제목 질문 분포), --apply 면 확신할 때만 반영
  python -m nhdip.cli kb-es [--sync|--rebuild|--check]  검색 엔진(Elasticsearch — 3-way 구성 설계 §24) 분석 결과 · 문서 색인 상태 · 동기화 · 처음부터 다시 올리기 · 점검(문제 있으면 종료 코드 1). 인자 없으면 상태
  python -m nhdip.cli es-password [--timeout 60]   내장 Elasticsearch 계정 비밀번호를 ES_PASSWORD 로 맞춤 (make es-password — 임시 관리 계정 환경변수 필요)
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from nhdip.db import SessionLocal


def _es_password(timeout: int) -> int:
    """ES 볼륨에 저장된 계정(ES_USER, 기본 elastic) 비밀번호를 환경변수 ES_PASSWORD 로 바꾼다 (Phase K · ES-02 · Q154).

    ES 는 ELASTIC_PASSWORD 를 볼륨을 처음 만들 때만 쓴다 — 그 뒤 .env 를 다시 만들면 api 는 401 을 받는다.
    임시 관리 계정(file realm, 환경변수 ES_RESET_USER · ES_RESET_PASSWORD — infra/scripts/es-sync-password.sh 가 만들고 지움)으로
    `_security/user/<계정>/_password` 를 호출한다. 비밀번호는 인자로 받지 않는다(프로세스 목록 노출 방지).
    """
    import os
    import time

    from nhdip.config import get_settings
    from nhdip.knowledge.elastic import make_client, safe_url

    st = get_settings()
    url, user, new = st.es_url.strip(), (st.es_user or "elastic").strip(), st.es_password
    if not url or not new:
        print("ES_URL · ES_PASSWORD 가 필요합니다(.env — make env)", file=sys.stderr)
        return 2
    with make_client(url, user, new, read_timeout=10.0) as c:
        try:
            if c.get("/_security/_authenticate").status_code == 200:
                print(json.dumps({"ok": True, "changed": False, "message": f"{user} 비밀번호가 이미 ES_PASSWORD 와 같습니다", "url": safe_url(url)}, ensure_ascii=False))
                return 0
        except Exception as exc:  # noqa: BLE001
            print(f"Elasticsearch 에 연결할 수 없습니다 — {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    via_user, via_pw = os.environ.get("ES_RESET_USER", ""), os.environ.get("ES_RESET_PASSWORD", "")
    if not via_user or not via_pw:
        print("임시 관리 계정(ES_RESET_USER · ES_RESET_PASSWORD)이 없습니다 — make es-password 로 실행하세요", file=sys.stderr)
        return 2
    deadline = time.monotonic() + max(5, timeout)
    last = ""
    with make_client(url, via_user, via_pw, read_timeout=15.0) as c:
        while time.monotonic() < deadline:
            try:
                r = c.post(f"/_security/user/{user}/_password", json={"password": new})
            except Exception as exc:  # noqa: BLE001
                last = f"{type(exc).__name__}: {exc}"
                time.sleep(2)
                continue
            if r.status_code == 200:
                break
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code != 401:  # 401 = 임시 계정이 아직 반영 전(file realm 은 몇 초마다 다시 읽음)
                print(f"비밀번호 변경 실패 — {last}", file=sys.stderr)
                return 1
            time.sleep(2)
        else:
            print(f"시간 안에 바꾸지 못했습니다 — {last}", file=sys.stderr)
            return 1
    with make_client(url, user, new, read_timeout=10.0) as c:
        ok = c.get("/_security/_authenticate").status_code == 200
    print(json.dumps({"ok": ok, "changed": True, "message": f"{user} 비밀번호를 ES_PASSWORD 로 맞췄습니다" if ok else "변경 후 확인 실패", "url": safe_url(url)}, ensure_ascii=False))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nhdip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("seed")
    sp.add_argument("--with-precompute", action="store_true")
    ap_rd = sub.add_parser("reset-data", help="업무 자료 비우기(기본은 미리보기)")
    ap_rd.add_argument("--yes", action="store_true", help="미리보기가 아니라 실제로 지운다(되돌릴 수 없음)")
    ap_rd.add_argument("--force", action="store_true", help="실행 중인 작업이 있어도 진행")
    ap_rd.add_argument("--keep-external", action="store_true", help="Elasticsearch · Neo4j 는 건드리지 않음(다음 동기화 · 재투영이 정리)")
    ap_rs = sub.add_parser("remove-seed-structure", help="예전 시드가 넣은 업무 구조(지표 · 업무 흐름 · 화면 연결 · 규칙 · 화면 · 조직 · 정의서 …) 정리 — 기본은 미리보기 (Phase O)")
    ap_rs.add_argument("--yes", action="store_true", help="미리보기가 아니라 실제로 지운다(먼저 make backup)")
    ap_cd = sub.add_parser("consolidate-datasets", help="같은 자료가 여러 정의(…_2 · …_3)로 갈라진 것을 업무 구성이 읽는 정의 하나로 모으고, 팀 소유로 들어간 영업점 판을 바로잡음 — 기본은 미리보기")
    ap_cd.add_argument("--yes", action="store_true", help="미리보기가 아니라 실제로 옮긴다(갈라진 정의는 사용 중지 · 이력 보존)")
    ap_bd = sub.add_parser("branch-diagnose", help="영업점 화면이 빈 이유를 단계별로(조직 · 필요한 자료의 그 지점 행 · 계산 대상 · 최근 실행 · 산출물)")
    ap_bd.add_argument("office", help="사무소 코드(예: BR301)")
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
    ap_es = sub.add_parser("kb-es")
    g_es = ap_es.add_mutually_exclusive_group()
    g_es.add_argument("--sync", action="store_true", help="PostgreSQL ↔ ES 목록을 대조해 다른 것만 올리고 사라진 것은 지움(분석 결과 · 문서 색인, 제한 없이 한 번에)")
    g_es.add_argument("--rebuild", action="store_true", help="두 색인을 지우고 처음부터 다시 올림(임베딩 차원 · 분석기가 바뀐 뒤)")
    g_es.add_argument("--check", action="store_true", help="3-way 검색 점검 — ES 연결 · 두 색인 동기화 · nori 를 확인해 문제가 있으면 종료 코드 1 (CI · 기동 직후)")
    ap_ep = sub.add_parser("es-password", help="내장 Elasticsearch 의 계정 비밀번호를 환경변수 ES_PASSWORD 로 맞춤 (make es-password 가 호출)")
    ap_ep.add_argument("--timeout", type=int, default=60, help="임시 계정이 ES 에 반영될 때까지 기다리는 초")
    args = ap.parse_args(argv)

    if args.cmd == "es-password":
        return _es_password(args.timeout)

    if args.cmd == "kb-es":
        from nhdip.knowledge import elastic

        if not elastic.configured():
            print("ES_URL 이 설정되지 않았습니다(기본은 PostgreSQL 검색).", file=sys.stderr)
            return 2
        try:
            with SessionLocal() as s:
                if args.rebuild:
                    rep = {"analysis": elastic.rebuild(s)}
                    s.commit()
                    rep["documents"] = elastic.rebuild_docs(s)
                    s.commit()
                elif args.sync:
                    rep = elastic.sync_all(s, limit=10**9, force=True)
                    s.commit()
                else:
                    rep = elastic.status(s)
                    if args.check:
                        ok, probs = elastic.healthy(rep)
                        rep = {"ok": ok, "problems": probs, "status": rep}
                        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
                        return 0 if ok else 1
        except elastic.EsUnavailable as exc:
            print(f"ES 오류: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        return 0

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
    if args.cmd == "remove-seed-structure":
        import json as _json

        from nhdip.bizconfig import cleanup

        with SessionLocal() as s:
            if not args.yes:
                p = cleanup.plan(s)
                print(_json.dumps({"preview": True, "counts": cleanup.summary(p), "orgs": p["orgs"], "workflows": p["workflows"], "rules": p["rules"], "screens": p["screens"],
                                   "settings": p["settings"], "emptyDatasets": p["emptyDatasets"], "ontology": p["ontology"], "hint": "지우려면 --yes (먼저 make backup)"}, ensure_ascii=False, indent=1))
                return 0
            out = cleanup.execute(s, "cli")
            s.commit()
            print(_json.dumps({"removed": out}, ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "branch-diagnose":
        from nhdip.views.branch_diag import diagnose

        with SessionLocal() as s:
            rep = diagnose(s, args.office)
        print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
        return 0 if rep.get("ok") else 1
    if args.cmd == "consolidate-datasets":
        from nhdip.data import consolidate

        with SessionLocal() as s:
            if not args.yes:
                print(json.dumps({"preview": True, "plan": consolidate.plan(s), "next": "옮기려면 --yes"}, ensure_ascii=False, indent=1, default=str))
                return 0
            rep = consolidate.execute(s, "cli")
            s.commit()
        print(json.dumps({"consolidated": rep}, ensure_ascii=False, indent=1, default=str))
        return 0
    if args.cmd == "reset-data":
        from nhdip.data import reset as R
        from nhdip.data.deletion import remove_files

        with SessionLocal() as s:
            pv = R.preview(s)
            if not args.yes:
                print(json.dumps({"preview": True, **pv, "next": "실제로 지우려면 --yes (make reset-data YES=1)"}, ensure_ascii=False, indent=1))
                return 2
            try:
                rep = R.reset_business_data(s, "cli", external=not args.keep_external, force=args.force)
            except R.ResetBusy as exc:
                s.rollback()
                print(str(exc), file=sys.stderr)
                return 3
            s.commit()
            files = remove_files(s, rep.files) if rep.files else {}
        print(json.dumps({"reset": True, **rep.as_dict(), "filesRemoved": files}, ensure_ascii=False, indent=1, default=str))
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
