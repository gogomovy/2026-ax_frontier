"use client";

import { AdminPage, Card, Collapse, JsonEditor, JsonView, Loading, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPost } from "@/lib/api-client";

interface Rule {
  code: string;
  name: string;
  kind: string;
  description: string;
  activeVersion: number;
  versions: { version: number; body: unknown; note: string | null; createdBy: string | null; createdAt: string }[];
}

/** 판정 규칙 · 임계값 · 가중치 · 반올림 (버전 관리, ADM-10) — 저장하면 관련 워크플로우가 다시 계산한다 */
export default function RulesAdmin() {
  const rules = useApiData<Rule[]>("/admin/rules");
  const { run, busy } = useAction();
  return (
    <AdminPage title="판정 규칙" description="규칙을 저장하면 새 버전이 활성화되고 rule.changed 이벤트로 이 규칙을 쓰는 워크플로우만 다시 실행됩니다. 과거 계산은 당시 버전으로 남습니다.">
      <Loading error={rules.error} loading={!rules.data && rules.loading} />
      {(rules.data ?? []).map((r) => {
        const active = r.versions.find((v) => v.version === r.activeVersion);
        return (
          <Card
            key={r.code}
            title={
              <span className="flex flex-wrap items-center gap-xs">
                {r.name} <code className="font-mono text-[11px] text-stone">{r.code}</code> <Badge>{r.kind}</Badge> <Badge tone="success">v{r.activeVersion} 적용</Badge>
              </span>
            }
          >
            <p className="mb-md text-[12.5px] text-steel">{r.description}</p>
            <JsonEditor value={active?.body ?? {}} rows={8} disabled={busy} label="새 버전으로 저장" onSave={(v) => run(() => apiPost(`/admin/rules/${r.code}/versions`, { body: v, note: "관리자 수정" }), "새 규칙 버전을 적용했습니다", rules.reload)} />
            <div className="mt-md">
              <Collapse label={`버전 이력 ${r.versions.length}건`}>
                <div className="flex flex-col gap-md">
                  {r.versions.map((v) => (
                    <div key={v.version} className="rounded-lg border border-hairline-soft p-md">
                      <div className="mb-xs flex flex-wrap items-center gap-xs text-[11.5px] text-steel">
                        <b className="text-ink-deep">v{v.version}</b> {v.createdBy ?? "-"} · {fmtTime(v.createdAt)} · {v.note ?? ""}
                        {v.version !== r.activeVersion ? (
                          <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost(`/admin/rules/${r.code}/activate`, { version: v.version }), `v${v.version} 을 적용했습니다`, rules.reload)}>
                            이 버전 적용
                          </Button>
                        ) : (
                          <Badge tone="success">적용 중</Badge>
                        )}
                      </div>
                      <JsonView value={v.body} maxHeight={160} />
                    </div>
                  ))}
                </div>
              </Collapse>
            </div>
          </Card>
        );
      })}
    </AdminPage>
  );
}
