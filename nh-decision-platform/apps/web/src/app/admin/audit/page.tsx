"use client";

import { useState } from "react";
import { AdminPage, C, Card, Collapse, JsonView, Loading, Table, TextInput, fmtTime, useApiData } from "@/components/admin/kit";
import { Badge } from "@/components/ui/primitives";

interface Row {
  id: number;
  at: string;
  actor: string | null;
  action: string;
  targetKind: string | null;
  targetId: string | null;
  detail: unknown;
  ip: string | null;
}

/** 감사 로그 — 로그인 · 권한 · 설정 · 데이터 · 목표/진행사업 변경 (ADM-14) */
export default function AuditAdmin() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const q = new URLSearchParams({ limit: "300", ...(actor ? { actor } : {}), ...(action ? { action } : {}) }).toString();
  const rows = useApiData<Row[]>(`/admin/audit?${q}`);
  return (
    <AdminPage title="감사 로그" description="누가 언제 무엇을 바꿨는지 기록합니다. 작업 접두어(예: auth. · admin.dataset · goal. · plan.)로 거를 수 있습니다.">
      <Card>
        <div className="mb-md flex flex-wrap gap-md">
          <TextInput label="사번" value={actor} onChange={setActor} mono />
          <TextInput label="작업 접두어" value={action} onChange={setAction} mono />
        </div>
        <Loading error={rows.error} loading={!rows.data && rows.loading} />
        <Table head={["시각", "사번", "작업", "대상", "IP", "상세"]}>
          {(rows.data ?? []).map((r) => (
            <tr key={r.id}>
              <C className="whitespace-nowrap text-[11.5px]">{fmtTime(r.at)}</C>
              <C mono>{r.actor ?? "-"}</C>
              <C>
                <Badge tone={r.action.includes("failed") ? "critical" : r.action.startsWith("admin.") ? "dark" : "neutral"}>{r.action}</Badge>
              </C>
              <C className="text-[11.5px]">
                {r.targetKind ?? ""} {r.targetId ?? ""}
              </C>
              <C mono>{r.ip ?? "-"}</C>
              <C className="min-w-[240px]">{r.detail ? <Collapse label="보기"><JsonView value={r.detail} maxHeight={200} /></Collapse> : "-"}</C>
            </tr>
          ))}
        </Table>
      </Card>
    </AdminPage>
  );
}
