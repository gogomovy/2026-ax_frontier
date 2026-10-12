"use client";

import { useMemo, useState } from "react";
import { AdminPage, Card, Collapse, JsonEditor, Loading, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { ValueView } from "@/components/admin/ValueView";
import { Advanced, EmptyState } from "@/components/ui/Layout";
import { Badge, PillTabs } from "@/components/ui/primitives";
import { apiPut } from "@/lib/api-client";

interface SettingRow {
  key: string;
  value: unknown;
  description: string;
  updatedBy: string | null;
  updatedAt: string;
}

/** 설정 키의 앞부분 → 묶음 이름 */
const GROUPS: Record<string, string> = {
  llm: "LLM · 비용",
  agents: "판단 에이전트",
  orchestrator: "오케스트레이터",
  workflow: "워크플로 실행",
  analysis: "분석 · 화면",
  assist: "질의 패널",
  contracts: "컬럼 정의서",
  upload: "업로드 · 보안",
  governance: "거버넌스",
  retention: "보관",
  alerts: "알림",
  ui: "화면 표시",
  branch: "영업점",
  risk: "신용리스크",
  screen: "화면 권한",
  calc: "계산",
  obs: "관측성",
  seed: "시드(자동)",
};
const groupOf = (key: string) => GROUPS[key.split(".")[0]] ?? "기타";

/** 값 요약 — JSON 을 펼치지 않고도 무엇이 들어 있는지 보이게 */
function summary(v: unknown): string {
  if (v === null || v === undefined) return "비어 있음";
  if (typeof v === "boolean") return v ? "켜짐" : "꺼짐";
  if (typeof v === "number" || typeof v === "string") return String(v).slice(0, 80) || "빈 문자열";
  if (Array.isArray(v)) return `목록 ${v.length}개`;
  const keys = Object.keys(v as object);
  return keys.length ? `${keys.slice(0, 5).join(" · ")}${keys.length > 5 ? ` 외 ${keys.length - 5}` : ""}` : "비어 있음";
}

/** 운영 설정 (Phase C · ADM-03) — 묶음 · 검색 · 값 요약 먼저, 편집은 항목마다 펼쳐서 */
export default function AdminSettings() {
  const settings = useApiData<SettingRow[]>("/admin/settings");
  const { run, busy } = useAction();
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("전체");
  const rows = useMemo(() => settings.data ?? [], [settings.data]);
  const groups = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((r) => m.set(groupOf(r.key), (m.get(groupOf(r.key)) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const shown = rows.filter((r) => (group === "전체" || groupOf(r.key) === group) && (!q || `${r.key} ${r.description}`.toLowerCase().includes(q.toLowerCase())));

  return (
    <AdminPage title="운영 설정" description="플랫폼 동작을 바꾸는 설정값입니다. 저장하면 즉시 반영되고 감사 로그에 남습니다. 설정마다 관련 워크플로가 다시 계산될 수 있습니다.">
      <Loading error={settings.error} loading={!settings.data && settings.loading} />
      {settings.data ? (
        <Card>
          <div className="mb-md flex flex-wrap items-end gap-md">
            <TextInput label="검색" value={q} onChange={setQ} placeholder="키 · 설명" className="w-[260px]" />
            <PillTabs
              size="sm"
              label="설정 묶음"
              value={group}
              onChange={setGroup}
              items={[{ key: "전체", label: "전체", count: rows.length }, ...groups.map(([g, n]) => ({ key: g, label: g, count: n }))]}
            />
          </div>
          {shown.length === 0 ? (
            <EmptyState compact title="조건에 맞는 설정이 없습니다" description="검색어나 묶음을 바꿔 보세요." />
          ) : (
            <ul className="flex flex-col divide-y divide-hairline-soft">
              {shown.map((row) => (
                <li key={row.key} className="py-md">
                  <div className="flex flex-wrap items-start justify-between gap-xs">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-[12.5px] font-bold text-ink-deep">{row.key}</span>
                        <Badge>{groupOf(row.key)}</Badge>
                      </p>
                      <p className="mt-0.5 max-w-[900px] text-[12px] leading-relaxed text-steel">{row.description}</p>
                    </div>
                    <p className="text-[11px] text-stone">
                      {row.updatedBy ?? "-"} · {fmtTime(row.updatedAt)}
                    </p>
                  </div>
                  <p className="mt-1 text-[12.5px] text-charcoal">
                    현재 값: <b className="font-medium">{summary(row.value)}</b>
                  </p>
                  {row.value !== null && typeof row.value === "object" ? (
                    <div className="mt-xs">
                      <Collapse label="값 펼쳐 보기">
                        <div className="rounded-lg border border-hairline-soft p-xs">
                          <ValueView value={row.value} />
                        </div>
                      </Collapse>
                    </div>
                  ) : null}
                  <div className="mt-xs">
                    <Advanced label="값 편집 (JSON)">
                      <JsonEditor
                        value={row.value}
                        rows={typeof row.value === "object" && row.value !== null ? 8 : 1}
                        disabled={busy}
                        onSave={(v) => run(() => apiPut<{ message?: string }>(`/admin/settings/${encodeURIComponent(row.key)}`, { value: v }), (r) => r?.message ?? "저장했습니다", settings.reload)}
                      />
                    </Advanced>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}
    </AdminPage>
  );
}
