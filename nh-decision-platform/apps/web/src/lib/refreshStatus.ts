/** 분석 갱신 상태 (Phase P · AGW-08) — `GET /analysis/status` 응답과 화면 문구 */
export interface WorkflowStatus {
  workflow: string;
  name: string;
  enabled: boolean;
  state: "idle" | "queued" | "held" | "approval" | "running";
  pending: { jobId: number; since: string | null; runAfter: string | null; causes: string[]; causeCount: number } | null;
  lastRun: { id: string; status: string; startedAt: string | null; finishedAt: string | null } | null;
  lastSuccessAt: string | null;
  triggers: {
    data: string[];
    team: string | null;
    common: boolean;
    events: string[];
    rules: string[];
    docClasses: string[];
    any: string[];
    cron: { expr: string; label: string; next: string; lastFiredAt: string | null }[];
    upstream: string[];
    downstream: number;
  };
}

const STATE_LABEL: Record<WorkflowStatus["state"], string> = {
  idle: "최신 상태",
  queued: "새 자료 반영 대기 중",
  held: "상위 분석 완료 대기 중",
  approval: "관리자 승인 대기 중",
  running: "다시 계산하는 중",
};

export function stateLabel(s: WorkflowStatus["state"]): string {
  return STATE_LABEL[s] ?? s;
}

/** 자동 갱신 조건 — 정기 실행 · 자료 변경 · 팀 · 공통 DB · 상위 지표 · 목표 · 규칙 순 */
export function refreshConditions(st: Pick<WorkflowStatus, "triggers">): string[] {
  const t = st.triggers;
  const out: string[] = [];
  for (const c of t.cron) out.push(c.label);
  if (t.data.length) out.push(t.data.length <= 2 ? `자료 변경 시(${t.data.join(" · ")})` : `자료 변경 시(${t.data.slice(0, 2).join(" · ")} 외 ${t.data.length - 2})`);
  if (t.team) out.push("우리 팀 새 자료 반영 시");
  if (t.common) out.push("공통 통합 DB 변경 시");
  if (t.upstream.length) out.push(`상위 분석 결과 변경 시(${t.upstream.slice(0, 2).join(" · ")})`);
  for (const e of t.events) out.push(`${e} 시`);
  if (t.rules.length) out.push("판정 규칙 변경 시");
  if (t.docClasses.length) out.push("관련 문서 반영 시");
  return Array.from(new Set(out));
}
