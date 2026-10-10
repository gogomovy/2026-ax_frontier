"""운영 알림 (작업 8.5) — 워커가 1분마다 상태를 훑어 조건에 맞으면 알림을 남기고(ops.alert) 채널로 보낸다.

기본 꺼짐: 설정 `alerts.policy.enabled=false` 이면 기록만(status=logged). 채널 주소 · 계정은 배포 환경변수로만 받는다.
  ALERT_WEBHOOK_URL  — JSON {text, alert} POST (Slack · Mattermost · 사내 메신저 웹훅 호환)
  ALERT_SMTP_HOST · ALERT_SMTP_PORT · ALERT_SMTP_USER · ALERT_SMTP_PASSWORD · ALERT_SMTP_FROM · ALERT_SMTP_TO(쉼표) · ALERT_SMTP_STARTTLS
조건(설정 alerts.policy.rules — 관리자 편집)
  workflow_failed · quality_failed · auth_failures(창 안 실패 횟수) · llm_budget(경고 %) · golden_failed
같은 알림은 dedupe 키로 한 번만 보낸다.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nhdip.models import AuditLog, Setting, WorkflowRun, source, utcnow
from nhdip.models.runtime import Alert

log = logging.getLogger("nhdip.alerts")
SEVERITY = {"info": 0, "warning": 1, "critical": 2}
DEFAULT_POLICY: dict[str, Any] = {
    "enabled": False,
    "channels": ["webhook", "email"],
    "min_severity": "warning",
    "lookback_min": 30,
    "rules": {
        "workflow_failed": {"enabled": True, "severity": "critical"},
        "quality_failed": {"enabled": True, "severity": "warning"},
        "auth_failures": {"enabled": True, "severity": "warning", "threshold": 10, "window_min": 10},
        "llm_budget": {"enabled": True, "severity": "warning", "levels": [80, 100]},
        "golden_failed": {"enabled": True, "severity": "warning"},
    },
}


def policy(session: Session) -> dict[str, Any]:
    s = session.get(Setting, "alerts.policy")
    v = s.value if s and isinstance(s.value, dict) else {}
    rules = {**DEFAULT_POLICY["rules"], **{k: {**DEFAULT_POLICY["rules"].get(k, {}), **r} for k, r in (v.get("rules") or {}).items()}}
    return {**DEFAULT_POLICY, **v, "rules": rules}


def _send_webhook(alert: Alert) -> str:
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return "skip"
    text = f"[{alert.severity.upper()}] {alert.title}"
    r = httpx.post(url, json={"text": text, "alert": {"kind": alert.kind, "severity": alert.severity, "title": alert.title, "detail": alert.detail, "traceId": alert.trace_id}}, timeout=10)
    r.raise_for_status()
    return "ok"


def _send_email(alert: Alert) -> str:
    host = os.environ.get("ALERT_SMTP_HOST", "").strip()
    to = [x.strip() for x in os.environ.get("ALERT_SMTP_TO", "").split(",") if x.strip()]
    if not host or not to:
        return "skip"
    msg = EmailMessage()
    msg["Subject"] = f"[NHDIP {alert.severity}] {alert.title}"
    msg["From"] = os.environ.get("ALERT_SMTP_FROM", "nhdip@localhost")
    msg["To"] = ", ".join(to)
    msg.set_content(f"{alert.title}\n\n{json.dumps(alert.detail, ensure_ascii=False, indent=1)}\n\n추적 ID: {alert.trace_id or '-'}")
    with smtplib.SMTP(host, int(os.environ.get("ALERT_SMTP_PORT", "25")), timeout=15) as smtp:
        if os.environ.get("ALERT_SMTP_STARTTLS", "1") == "1":
            smtp.starttls()
        if os.environ.get("ALERT_SMTP_USER"):
            smtp.login(os.environ["ALERT_SMTP_USER"], os.environ.get("ALERT_SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    return "ok"


SENDERS = {"webhook": _send_webhook, "email": _send_email}


def raise_alert(session: Session, kind: str, severity: str, title: str, detail: dict[str, Any], dedupe_key: str, *, force: bool = False) -> Alert | None:
    """알림 1건 — 같은 dedupe 키가 있으면 다시 만들지 않는다(force=시험 발송)."""
    if not force and session.execute(select(Alert.id).where(Alert.dedupe_key == dedupe_key).limit(1)).scalar():
        return None
    pol = policy(session)
    a = Alert(kind=kind, severity=severity, title=title[:300], detail=detail, dedupe_key=dedupe_key[:200], channels={}, status="logged")
    session.add(a)
    session.flush()
    if not pol["enabled"] and not force:
        return a
    if SEVERITY.get(severity, 0) < SEVERITY.get(pol["min_severity"], 1) and not force:
        a.status = "below_threshold"
        return a
    results: dict[str, str] = {}
    for ch in pol["channels"]:
        fn = SENDERS.get(ch)
        if not fn:
            continue
        try:
            results[ch] = fn(a)
        except Exception as exc:  # noqa: BLE001 — 채널 장애는 기록만
            results[ch] = f"error: {type(exc).__name__}: {str(exc)[:200]}"
            log.warning("alert channel %s failed: %s", ch, exc)
    a.channels = results
    sent = [v for v in results.values() if v == "ok"]
    a.status = "sent" if sent else ("failed" if any(v.startswith("error") for v in results.values()) else "no_channel")
    return a


def scan(session: Session) -> int:
    """조건 검사 — 워커 루프에서 1분마다. 반환: 새로 만든 알림 수."""
    pol = policy(session)
    rules = pol["rules"]
    since = utcnow() - timedelta(minutes=int(pol["lookback_min"]))
    n = 0

    def add(*args, **kw):
        nonlocal n
        if raise_alert(session, *args, **kw) is not None:
            n += 1

    if rules["workflow_failed"].get("enabled"):
        for r in session.execute(select(WorkflowRun).where(WorkflowRun.status == "failed", WorkflowRun.started_at >= since)).scalars():
            add("workflow_failed", rules["workflow_failed"]["severity"], f"워크플로우 실패 — {r.workflow_code}", {"run": r.id, "error": (r.error or "")[:500], "traceId": r.trace_id}, f"workflow_failed:{r.id}")
    if rules["quality_failed"].get("enabled"):
        for origin in ("bank", "ext"):
            t = source(origin)
            for v in session.execute(select(t.version).where(t.version.created_at >= since, t.version.status.in_(["rejected"]))).scalars():
                bad = [c for c in (v.quality or {}).get("checks", []) if not c.get("passed")][:5]
                add("quality_failed", rules["quality_failed"]["severity"], f"데이터 품질 검증 실패 — {v.dataset_code} v{v.version}", {"origin": origin, "dataset": v.dataset_code, "version": v.version, "checks": bad}, f"quality_failed:{origin}:{v.id}")
    ar = rules["auth_failures"]
    if ar.get("enabled"):
        win = int(ar.get("window_min", 10))
        cnt = session.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action.in_(["auth.login_failed", "auth.sso_failed"]), AuditLog.at >= utcnow() - timedelta(minutes=win))).scalar() or 0
        if cnt >= int(ar.get("threshold", 10)):
            bucket = utcnow().strftime("%Y%m%d%H") + f"{utcnow().minute // win:02d}"
            add("auth_failures", ar["severity"], f"로그인 실패 급증 — 최근 {win}분 {cnt}건", {"count": cnt, "window_min": win}, f"auth_failures:{bucket}")
    lr = rules["llm_budget"]
    if lr.get("enabled"):
        from nhdip.llm.budget import status as budget_status

        st = budget_status(session)
        if st["maxPct"] is not None:
            for level in sorted(lr.get("levels", [80, 100])):
                if st["maxPct"] >= level:
                    sev = "critical" if level >= 100 else lr["severity"]
                    add("llm_budget", sev, f"LLM 예산 {level}% 도달 — 이번 달 {st['maxPct']}%", {"maxPct": st["maxPct"], "tokens": st["usage"]["tokens"], "cost": st["usage"]["cost"]}, f"llm_budget:{st['usage']['since'][:7]}:{level}")
    if rules["golden_failed"].get("enabled"):
        from nhdip.views.store import get_current

        rep = get_current(session, "eval.golden")
        if isinstance(rep, dict) and rep.get("passed") is False:
            failed = [k for k, v in (rep.get("categories") or {}).items() if not v.get("ok")]
            add("golden_failed", rules["golden_failed"]["severity"], f"골든셋 평가 기준 미달 — {', '.join(failed)}", {"at": rep.get("at"), "failed": failed}, f"golden_failed:{rep.get('at')}")
    session.commit()
    return n
