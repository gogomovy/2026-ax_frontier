"use client";
import { AdminPage, C, Card, Collapse, JsonView, Loading, StatusBadge, Table, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

interface AlertItem {
  id: number;
  at: string;
  kind: string;
  severity: "info" | "warning" | "critical";
  title: string;
  detail: unknown;
  status: string;
  channels: Record<string, string>;
  traceId: string | null;
}
interface AlertsData {
  policy: { enabled: boolean; channels: string[]; min_severity: string; rules: Record<string, Record<string, unknown>> };
  channelsConfigured: Record<string, boolean>;
  items: AlertItem[];
}
interface Usage {
  budget: { monthly_tokens: number; monthly_cost: number; on_exceed: string };
  usage: { since: string; tokens: number; cost: number; items: { agent: string | null; model: string | null; calls: number; tokens: number; cost: number }[] };
  tokensPct: number | null;
  costPct: number | null;
  maxPct: number | null;
}
const SEV_TONE = { info: "neutral", warning: "attention", critical: "critical" } as const;

/** 운영 알림 · LLM 비용 (작업 8.5 · 4.7) */
export default function AlertsAdmin() {
  const alerts = useApiData<AlertsData>("/admin/alerts?limit=100");
  const usage = useApiData<Usage>("/admin/llm/usage");
  const { busy, run } = useAction();
  const p = alerts.data?.policy;
  const u = usage.data;
  return (
    <AdminPage
      title="운영 알림 · 비용"
      description="워커가 1분마다 워크플로우 실패 · 데이터 품질 실패 · 로그인 실패 급증 · LLM 예산 · 골든셋 미달을 확인해 알림을 남깁니다. 켜기와 조건은 설정 alerts.policy, 채널 주소는 배포 환경변수(ALERT_WEBHOOK_URL · ALERT_SMTP_*)입니다."
      actions={
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => apiPost("/admin/alerts/scan"), "지금 확인했습니다", alerts.reload)}>
            지금 확인
          </Button>
          <Button size="sm" variant="confirm" disabled={busy} onClick={() => run(() => apiPost("/admin/alerts/test"), "시험 알림을 보냈습니다", alerts.reload)}>
            시험 알림
          </Button>
        </div>
      }
    >
      <Card title="상태">
        <Loading error={alerts.error} loading={!alerts.data && alerts.loading} />
        {p ? (
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]" data-alert-policy>
            <Badge tone={p.enabled ? "success" : "neutral"}>{p.enabled ? "알림 켜짐" : "알림 꺼짐(기록만)"}</Badge>
            <span>최소 심각도 {p.min_severity}</span>
            {Object.entries(alerts.data?.channelsConfigured ?? {}).map(([ch, ok]) => (
              <Badge key={ch} tone={ok ? "info" : "neutral"}>
                {ch} {ok ? "설정됨" : "미설정"}
              </Badge>
            ))}
            <span className="text-stone">조건: {Object.entries(p.rules).filter(([, r]) => r.enabled).map(([k]) => k).join(" · ")}</span>
          </div>
        ) : null}
      </Card>

      <Card title={`LLM 사용량 · 예산 (${u ? fmtTime(u.usage.since).slice(0, 7) : "이번 달"} ~)`}>
        <Loading error={usage.error} loading={!u && usage.loading} />
        {u ? (
          <>
            <p className="mb-md text-[12.5px] text-charcoal" data-llm-usage>
              토큰 {u.usage.tokens.toLocaleString("ko-KR")}
              {u.budget.monthly_tokens ? ` / ${u.budget.monthly_tokens.toLocaleString("ko-KR")} (${u.tokensPct}%)` : " (한도 없음)"} · 금액 {u.usage.cost.toLocaleString("ko-KR")}원
              {u.budget.monthly_cost ? ` / ${u.budget.monthly_cost.toLocaleString("ko-KR")}원 (${u.costPct}%)` : ""} · 초과 시 {u.budget.on_exceed === "block" ? "호출 차단" : "알림만"}
            </p>
            <Table head={["에이전트", "모델", "호출", "토큰", "금액(원)"]}>
              {u.usage.items.map((i, k) => (
                <tr key={k}>
                  <C mono>{i.agent ?? "-"}</C>
                  <C mono>{i.model ?? "-"}</C>
                  <C right>{i.calls}</C>
                  <C right>{i.tokens.toLocaleString("ko-KR")}</C>
                  <C right>{i.cost.toLocaleString("ko-KR")}</C>
                </tr>
              ))}
            </Table>
          </>
        ) : null}
      </Card>

      <Card title="최근 알림">
        <Table head={["시각", "심각도", "내용", "상태", "채널", "상세"]}>
          {(alerts.data?.items ?? []).map((a) => (
            <tr key={a.id}>
              <C className="whitespace-nowrap text-[11.5px]">{fmtTime(a.at)}</C>
              <C>
                <Badge tone={SEV_TONE[a.severity] ?? "neutral"}>{a.severity}</Badge>
              </C>
              <C className="text-[12.5px]">{a.title}</C>
              <C>
                <StatusBadge status={a.status} />
              </C>
              <C className="text-[11px]">{Object.entries(a.channels ?? {}).map(([k, v]) => `${k}:${v}`).join(" · ") || "-"}</C>
              <C className="min-w-[200px]">
                <Collapse label="보기">
                  <JsonView value={a.detail} maxHeight={200} />
                </Collapse>
              </C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
