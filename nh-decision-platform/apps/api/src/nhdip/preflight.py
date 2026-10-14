"""운영 준비 점검 (B.34) — 운영에 올리기 전 · 운영 중에 설정 · 상태가 권장값과 맞는지 한 번에 본다.

  python -m nhdip.cli preflight      (make preflight — fail 이 있으면 종료 코드 1)
  GET /admin/readiness               (관리자 [시스템 상태] 화면)

각 항목: level = ok · warn(권장과 다름 · 시연 환경에서는 무방) · fail(운영에서 위험)과 고치는 방법(fix).
점검만 하고 아무것도 바꾸지 않는다. 비밀값은 결과에 넣지 않는다.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from nhdip.config import DEFAULT_SESSION_SECRET, get_settings
from nhdip.models import AppUser, AuditLog, LlmConnection, LlmProfile, Setting, WorkerHeartbeat, utcnow


HNSW_ADVISE_CHUNKS = 20_000  # 이 개수 이상 임베딩되면 부분 HNSW 인덱스를 권한다


def _setting(session: Session, key: str, default: Any = None) -> Any:
    s = session.get(Setting, key)
    return s.value if s is not None and s.value is not None else default


def _item(key: str, label: str, level: str, message: str, fix: str = "") -> dict[str, Any]:
    return {"key": key, "label": label, "level": level, "message": message, "fix": fix}


def run_checks(session: Session) -> dict[str, Any]:
    st = get_settings()
    out: list[dict[str, Any]] = []
    prod = st.nhdip_env == "prod"
    add = out.append

    add(_item("env", "실행 모드", "ok" if prod else "warn", f"NHDIP_ENV={st.nhdip_env}", "" if prod else ".env 에 NHDIP_ENV=prod (compose 기본값)"))
    weak = st.session_secret == DEFAULT_SESSION_SECRET or len(st.session_secret) < 32
    add(_item("session_secret", "세션 서명 키", "fail" if weak else "ok", "기본값 · 짧은 키" if weak else "32자 이상 무작위", "make env 로 SESSION_SECRET 생성" if weak else ""))

    # DB 계정 — api 가 소유자가 아닌 앱 계정으로 접속하는지
    try:
        cur = session.execute(text("SELECT current_user")).scalar()
        owner = session.execute(text("SELECT tableowner FROM pg_tables WHERE schemaname='audit' AND tablename='audit_log'")).scalar()
    except Exception:  # noqa: BLE001
        cur = owner = None
    if st.app_db_password and cur and owner and cur != owner:
        add(_item("db_role", "API DB 계정", "ok", f"api 는 {cur}(데이터 조작만) 로 접속 · 표 소유자 {owner}"))
    else:
        add(_item("db_role", "API DB 계정", "warn", f"api 가 표 소유자 계정({cur or '-'})으로 접속 — 감사 로그 보호를 우회할 수 있음", ".env 의 APP_DB_PASSWORD 를 채우고(make env) 재기동"))

    # 웹 보안
    https = st.cookie_secure or any(o.strip().startswith("https://") for o in st.trusted_origins.split(","))
    if st.trusted_origins and any(o.strip().startswith("https://") for o in st.trusted_origins.split(",")) and not st.cookie_secure:
        add(_item("cookie_secure", "HTTPS 쿠키", "fail", "HTTPS 주소인데 COOKIE_SECURE=0 — 세션 쿠키가 http 로도 전송됨", ".env 에 COOKIE_SECURE=1"))
    elif https:
        add(_item("cookie_secure", "HTTPS 쿠키", "ok", "COOKIE_SECURE=1 (Secure 쿠키 · HSTS)"))
    else:
        add(_item("cookie_secure", "HTTPS 쿠키", "warn", "http 로 서비스 중 — 로그인 비밀번호 · 세션이 암호화되지 않음", "앞단(ALB · nginx)에 인증서를 붙이고 COOKIE_SECURE=1 · TRUSTED_ORIGINS=https://<도메인>"))
    add(_item("trusted_origins", "변경 요청 허용 출처", "ok" if st.trusted_origins else "warn", st.trusted_origins or "비어 있음 — 같은 출처(Host)만 허용", "" if st.trusted_origins else "도메인으로 서비스하면 TRUSTED_ORIGINS=https://<도메인>"))
    from nhdip.config import docs_enabled

    if docs_enabled(st) and prod:
        add(_item("api_docs", "API 문서", "warn", "운영에서 /docs 공개 중", ".env 의 API_DOCS 를 비우거나 false"))
    else:
        add(_item("api_docs", "API 문서", "ok", "꺼짐" if not docs_enabled(st) else "켜짐(개발 모드)"))

    # 계정
    from nhdip.security import verify_password

    admin = session.get(AppUser, st.bootstrap_admin_emp_no)
    if admin is not None and st.bootstrap_admin_password and verify_password(st.bootstrap_admin_password, admin.password_hash):
        add(_item("admin_password", "최초 관리자 비밀번호", "warn", f"{admin.emp_no} 가 .env 의 최초 비밀번호를 그대로 사용", "관리자 [사용자] 에서 비밀번호 변경"))
    else:
        add(_item("admin_password", "최초 관리자 비밀번호", "ok", "변경됨"))
    demo = session.execute(select(func.count()).select_from(AppUser).where(AppUser.emp_no.in_(["20250001", "20250002", "20250003"]), AppUser.status == "active")).scalar() or 0
    add(_item("demo_users", "시연용 계정", "warn" if demo else "ok", f"시연용 계정 {demo}개 사용 중" if demo else "없음", "관리자 [사용자] 에서 20250001~3 사용 중지, .env 의 DEMO_USER_PASSWORD 비우기" if demo else ""))
    admins = session.execute(select(func.count()).select_from(AppUser).where(AppUser.role == "admin", AppUser.status == "active")).scalar() or 0
    dual = bool((_setting(session, "governance.dual_control", {}) or {}).get("enabled"))
    add(_item("admins", "관리자 수", "warn" if admins < 2 else "ok", f"활성 관리자 {admins}명" + (" · 이중 승인 켜짐" if dual else ""), "잠금 · 퇴사에 대비해 관리자를 2명 이상 두기 (이중 승인을 켜려면 필수)" if admins < 2 else ""))

    # LLM
    conn = session.execute(select(LlmConnection).where(LlmConnection.active)).scalars().first()
    prof = session.execute(select(LlmProfile).where(LlmProfile.is_default)).scalars().first()
    if conn is None or not (conn.base_url or "").strip() or prof is None or not (prof.model or "").strip():
        add(_item("llm", "LLM 연결", "warn", "연결 · 기본 모델이 없음 — 수치는 정상, 서술 · 판단은 규칙 · 기존 문장으로 대체", "관리자 [LLM 연동] 에서 연결 키 · 모델 입력"))
    else:
        from nhdip.security import decrypt_secret

        try:
            has_key = bool(decrypt_secret(conn.api_key_enc))
        except Exception:  # noqa: BLE001
            has_key = False
        add(_item("llm", "LLM 연결", "ok" if has_key else "warn", f"{conn.name} · 모델 {prof.model}" + ("" if has_key else " · 키 없음"), "" if has_key else "관리자 [LLM 연동] 에서 키 입력"))

    # 파일 저장소 (Phase C) — 업무 자료 요청 파일 · 업로드 원본 보관. 쓸 수 없으면 자료 올리기가 503
    import os as _os
    import tempfile

    fs_dir = st.filestore_dir
    try:
        _os.makedirs(fs_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=fs_dir, prefix=".probe-", delete=True):
            pass
        add(_item("filestore", "파일 저장소", "ok", f"{fs_dir} 쓰기 가능"))
    except OSError as exc:
        add(_item("filestore", "파일 저장소", "fail", f"{fs_dir} 에 쓸 수 없음 — {exc.__class__.__name__}", "docker compose up -d files-init (볼륨 권한 정리) 후 api · worker 재기동"))

    # 질문하기 지식 색인 (Phase D · 설계 §21) — 비었거나 뒤처지면 질문하기가 분석 결과를 찾지 못한다 (경고만: 수치 · 화면은 정상)
    try:
        from nhdip.knowledge.maintenance import status as kb_status

        kb = kb_status(session)
        tot, behind = kb["totals"], kb["stale"]["count"]
        loose = (kb["collections"].get("analysis.unassigned") or {}).get("chunks", 0)
        sub = f"청크 {tot['chunks']} · 임베딩 {tot['embedded']}/{tot['chunks']}"
        from nhdip.knowledge.calibration import calibrated_model

        cal_model = calibrated_model(session)
        used_model = session.execute(text("SELECT embedding_model FROM app.kb_chunk WHERE embedding IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")).scalar() if tot["embedded"] else None
        if tot["chunks"] == 0:
            add(_item("knowledge_index", "AI 어시스턴트 색인", "warn", "분석 결과 색인이 비어 있음 — 질문하기가 분석 결과로 답하지 못함", "python -m nhdip.cli seed (또는 관리자 API POST /admin/knowledge/reindex)"))
        elif behind or loose:
            add(_item("knowledge_index", "AI 어시스턴트 색인", "warn", f"{sub} · 뒤처진 산출물 {behind}건 · 미분류 청크 {loose}건", "워커가 1분 안에 따라잡음. 계속되면 워커 로그 확인 · 미분류는 관리자 컬렉션 규칙 지정"))
        elif cal_model and used_model and cal_model != used_model:
            # 코사인 거리 눈금은 모델마다 달라(설계 §21.15) 보정 때와 다른 모델이면 의미 기준(max_cosine_distance)이 맞지 않는다
            add(_item("knowledge_index", "AI 어시스턴트 색인", "warn", f"{sub} · 임베딩 모델이 보정 때와 다름({cal_model} → {used_model}) — 의미 검색 기준이 맞지 않을 수 있음", "python -m nhdip.cli kb-calibrate (결과 확인 후 --apply) 또는 관리자 [색인 · 컬렉션] 의 거리 보정"))
        elif tot["embedded"] >= HNSW_ADVISE_CHUNKS and not _setting(session, "knowledge.search", {}).get("hnsw_dim"):
            # 합성 부하 측정(설계 §21.14): 임베딩 10만 건에서 순차 탐색 400~570ms, 부분 HNSW 인덱스를 쓰면 한 자릿수 ms
            add(_item("knowledge_index", "AI 어시스턴트 색인", "warn", f"{sub} · 의미 검색이 순차 탐색 중(임베딩 {HNSW_ADVISE_CHUNKS:,}건 이상)", "python -m nhdip.cli kb-hnsw --dim <임베딩 차원> (모델이 확정된 뒤 한 번)"))
        else:
            note = "" if not tot["pendingEmbedding"] else " · 의미 검색은 임베딩 모델 연결 후 채워짐"
            if used_model and not cal_model:
                note += f" · 거리 기준 미보정({used_model}) — kb-calibrate 권장"
            add(_item("knowledge_index", "AI 어시스턴트 색인", "ok", sub + note))
    except Exception as exc:  # noqa: BLE001 — 점검 자체가 실패해도 나머지 점검은 계속
        session.rollback()
        add(_item("knowledge_index", "AI 어시스턴트 색인", "warn", f"상태를 읽지 못함 — {exc.__class__.__name__}", "마이그레이션 0014 적용 여부 확인 (alembic upgrade head)"))

    # 검색 엔진(3-way 구성 · 설계 §24) — PostgreSQL 원장 · Elasticsearch 키워드/의미 · Neo4j 그래프. 'pg' 로 정하고 ES 도 없으면 항목을 만들지 않는다.
    # ES 가 없거나 안 되면 검색은 PostgreSQL 로 축소 동작하므로 실패(fail)가 아니라 경고(warn)
    try:
        from nhdip.knowledge import elastic

        mode = elastic.backend_mode(session)
        if elastic.configured() or mode != "pg":
            if not elastic.configured():
                add(_item("search_backend", "AI 어시스턴트 검색 엔진", "warn",
                          ("검색 설정이 ES 인데 ES_URL 이 비어 있음" if mode == "es" else "3-way 표준 구성 아님 — ES_URL 미설정") + " · 키워드 · 의미 검색을 PostgreSQL 로 축소 동작 중",
                          "docker compose 기본 구성(elasticsearch 서비스 · ES_URL=http://elasticsearch:9200) 확인 후 api · worker 재기동, 또는 검색 설정 knowledge.search.backend 를 pg 로"))
            else:
                es = elastic.status(session)
                ok, probs = elastic.healthy(es)
                d = es.get("documents") or {}
                summary = f"분석 결과 {es.get('es_docs')}/{es.get('pg_chunks')} · 문서 {d.get('es_docs')}/{d.get('pg_chunks')} · 사용자 사전 {(es.get('state') or {}).get('dictionary') or 0}낱말"
                if ok:
                    add(_item("search_backend", "AI 어시스턴트 검색 엔진", "ok", f"Elasticsearch 연결됨 · {summary} · " + ("사용 중" if mode != "pg" else "준비됨(검색 설정은 pg)")))
                elif not es.get("up"):
                    add(_item("search_backend", "AI 어시스턴트 검색 엔진", "warn" if mode != "pg" else "ok", "; ".join(probs) + (" · PostgreSQL 로 폴백 중" if mode != "pg" else ""),
                              "make es-password(내장 ES 비밀번호를 .env 와 맞춤) 또는 관리자 [AI 어시스턴트 색인 › 연결 설정]" if es.get("errorKind") == "auth" else "ES 기동 · ES_URL · 인증 확인"))
                else:
                    add(_item("search_backend", "AI 어시스턴트 검색 엔진", "warn" if mode != "pg" else "ok", "; ".join(probs) + f" ({summary}) — 새 청크는 PostgreSQL 로 보충",
                              "워커 주기 안에 따라잡음. 계속되면 python -m nhdip.cli kb-es --sync (nori 없음이면 analysis-nori 설치 후 kb-es --rebuild)"))
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        add(_item("search_backend", "AI 어시스턴트 검색 엔진", "warn", f"상태를 읽지 못함 — {exc.__class__.__name__}"))

    # 운영 상태
    alive = session.execute(select(func.count()).select_from(WorkerHeartbeat).where(WorkerHeartbeat.seen_at > utcnow() - timedelta(seconds=60))).scalar() or 0
    add(_item("worker", "워커", "ok" if alive else "fail", f"동작 중 {alive}개", "" if alive else "docker compose logs worker 확인 후 docker compose up -d worker"))
    import os

    ap = _setting(session, "alerts.policy", {}) or {}
    channel = bool(os.environ.get("ALERT_WEBHOOK_URL") or (os.environ.get("ALERT_SMTP_HOST") and os.environ.get("ALERT_SMTP_TO")))
    if ap.get("enabled") and channel:
        add(_item("alerts", "운영 알림", "ok", "켜짐 · 채널 연결"))
    else:
        add(_item("alerts", "운영 알림", "warn", ("켜짐 · 채널 없음(기록만)" if ap.get("enabled") else "꺼짐(기록만)"), "관리자 설정 alerts.policy.enabled=true + .env 의 ALERT_WEBHOOK_URL 또는 ALERT_SMTP_*"))
    max_age = float(_setting(session, "ops.backup_max_age_days", 1) or 1)
    last = session.execute(select(func.max(AuditLog.at)).where(AuditLog.action == "ops.backup")).scalar()
    if last is None:
        add(_item("backup", "백업", "warn", "백업 기록 없음", "make backup (매일 실행 권장 — README 의 cron 예시)"))
    else:
        age = (utcnow() - last).total_seconds() / 86400
        add(_item("backup", "백업", "ok" if age <= max_age else "warn", f"마지막 백업 {last.isoformat(timespec='minutes')} ({age:.1f}일 전)", "" if age <= max_age else f"{max_age:g}일 넘음 — make backup · cron 확인"))
    ret = _setting(session, "retention.policy", {}) or {}
    add(_item("retention", "보관 기간 정리", "ok" if ret.get("enabled", True) else "warn", "켜짐" if ret.get("enabled", True) else "꺼짐 — 운영 기록이 계속 쌓임", "" if ret.get("enabled", True) else "설정 retention.policy.enabled=true"))

    counts = {lv: sum(1 for x in out if x["level"] == lv) for lv in ("ok", "warn", "fail")}
    return {"at": utcnow().isoformat(timespec="seconds"), "items": out, "counts": counts, "ready": counts["fail"] == 0}
