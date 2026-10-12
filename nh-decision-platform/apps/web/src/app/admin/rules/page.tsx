"use client";

import { useState } from "react";
import { AdminPage, Card, Collapse, JsonEditor, JsonView, Loading, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { ValueView } from "@/components/admin/ValueView";
import { Advanced, EmptyState } from "@/components/ui/Layout";
import { Badge, Button, PillTabs } from "@/components/ui/primitives";
import { StatCard, StatGrid } from "@/components/ui/StatCard";
import { apiPost } from "@/lib/api-client";

interface Rule {
  code: string;
  name: string;
  kind: string;
  description: string;
  activeVersion: number;
  dualControl?: boolean;
  versions: { version: number; body: unknown; note: string | null; createdBy: string | null; createdAt: string; pending?: boolean }[];
}

const KIND_LABEL: Record<string, string> = { threshold: "임계값", weight: "가중치", rounding: "반올림", grade: "등급", scope: "범위", mapping: "대응표", policy: "정책" };

/** 판정 규칙 · 임계값 · 가중치 · 반올림 (버전 관리, ADM-10 · ADM-03) — 구조화 보기 먼저, JSON 편집은 고급에 */
export default function RulesAdmin() {
  const rules = useApiData<Rule[]>("/admin/rules");
  const { run, busy } = useAction();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("전체");
  const all = rules.data ?? [];
  const kinds = Array.from(new Set(all.map((r) => r.kind)));
  const list = all.filter((r) => (kind === "전체" || r.kind === kind) && (!q || `${r.code} ${r.name} ${r.description}`.toLowerCase().includes(q.toLowerCase())));
  const pending = all.filter((r) => r.versions.some((v) => v.pending)).length;
  const dual = all.filter((r) => r.dualControl).length;

  return (
    <AdminPage
      title="판정 규칙"
      description="규칙을 저장하면 새 버전이 적용되고(rule.changed) 이 규칙을 쓰는 워크플로만 다시 계산합니다. 과거 계산은 당시 버전으로 남습니다. 이중 승인 규칙은 다른 관리자가 적용해야 반영됩니다."
      summary={
        <StatGrid columns={3} label="규칙 요약">
          <StatCard label="규칙" value={all.length || "-"} unit="개" hint={`종류 ${kinds.length}가지`} />
          <StatCard label="승인 대기 버전" value={pending} unit="개" tone={pending ? "attention" : "default"} hint={pending ? "다른 관리자의 적용이 필요" : "대기 없음"} />
          <StatCard label="이중 승인 규칙" value={dual} unit="개" hint="저장한 사람과 적용하는 사람이 달라야 함" />
        </StatGrid>
      }
    >
      <div className="mb-md flex flex-wrap items-end gap-md">
        <TextInput label="찾기" value={q} onChange={setQ} placeholder="코드 · 이름 · 설명" className="w-[260px]" />
        <PillTabs size="sm" label="규칙 종류" value={kind} onChange={setKind} items={[{ key: "전체", label: "전체", count: all.length }, ...kinds.map((k) => ({ key: k, label: KIND_LABEL[k] ?? k, count: all.filter((r) => r.kind === k).length }))]} />
      </div>
      <Loading error={rules.error} loading={!rules.data && rules.loading} />
      {rules.data && !list.length ? <EmptyState title="맞는 규칙이 없습니다" description="찾는 말이나 종류를 바꿔 보세요." /> : null}
      {list.map((r) => {
        const active = r.versions.find((v) => v.version === r.activeVersion);
        return (
          <Card
            key={r.code}
            title={
              <span className="flex flex-wrap items-center gap-xs">
                {r.name} <code className="font-mono text-[11px] text-stone">{r.code}</code> <Badge>{KIND_LABEL[r.kind] ?? r.kind}</Badge> <Badge tone="success">v{r.activeVersion} 적용</Badge>
                {r.dualControl ? <Badge tone="warning">이중 승인</Badge> : null}
                {r.versions.some((v) => v.pending) ? <Badge tone="attention">승인 대기</Badge> : null}
              </span>
            }
          >
            <p className="mb-md text-[12.5px] text-steel">{r.description}</p>
            <div className="mb-md rounded-xl border border-hairline-soft p-md" data-rule-body>
              <p className="mb-xs text-[11.5px] font-bold text-steel">
                현재 적용 값 (v{r.activeVersion}
                {active ? ` · ${active.createdBy ?? "-"} · ${fmtTime(active.createdAt)}` : ""})
              </p>
              <ValueView value={active?.body ?? {}} />
            </div>
            <div className="flex flex-col gap-xs">
              <Advanced label="고급 — JSON 으로 고쳐 새 버전 저장">
                <JsonEditor
                  value={active?.body ?? {}}
                  rows={8}
                  disabled={busy}
                  label="새 버전으로 저장"
                  onSave={(v) => run(() => apiPost(`/admin/rules/${r.code}/versions`, { body: v, note: "관리자 수정" }), r.dualControl ? "새 버전을 저장했습니다 — 다른 관리자가 적용하면 반영됩니다(이중 승인)" : "새 규칙 버전을 적용했습니다", rules.reload)}
                />
              </Advanced>
              <Collapse label={`버전 이력 ${r.versions.length}건`}>
                <div className="flex flex-col gap-md">
                  {r.versions.map((v) => (
                    <div key={v.version} className="rounded-lg border border-hairline-soft p-md">
                      <div className="mb-xs flex flex-wrap items-center gap-xs text-[11.5px] text-steel">
                        <b className="text-ink-deep">v{v.version}</b> {v.createdBy ?? "-"} · {fmtTime(v.createdAt)} · {v.note ?? ""}
                        {v.pending ? <Badge tone="warning">승인 대기</Badge> : null}
                        {v.version !== r.activeVersion ? (
                          <Button size="sm" variant="quiet" disabled={busy} onClick={() => run(() => apiPost(`/admin/rules/${r.code}/activate`, { version: v.version }), `v${v.version} 을 적용했습니다`, rules.reload)}>
                            이 버전 적용
                          </Button>
                        ) : (
                          <Badge tone="success">적용 중</Badge>
                        )}
                      </div>
                      <ValueView value={v.body} />
                      <div className="mt-xs">
                        <Advanced label="원본(JSON)">
                          <JsonView value={v.body} maxHeight={160} />
                        </Advanced>
                      </div>
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
