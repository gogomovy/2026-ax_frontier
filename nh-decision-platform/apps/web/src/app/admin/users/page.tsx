"use client";

import { useMemo, useState } from "react";
import { AdminPage, C, Card, Check, Loading, Select, StatusBadge, Table, Tabs, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";

interface UserRow {
  empNo: string;
  name: string;
  position: string | null;
  role: "admin" | "user";
  status: string;
  org: { code: string; name: string };
  orgPath: { code: string; name: string; levelLabel: string }[];
  failedCount: number;
  createdAt: string;
  lastLoginAt: string | null;
  approvedBy: string | null;
  /** 부서 데이터 책임자 (UPL-04 · Q107) */
  dataSteward?: boolean;
  stewardScope?: { code: string; name: string } | null;
}
interface OrgRow {
  code: string;
  name: string;
  level: number;
  parent: string | null;
  active: boolean;
}

const STATUS_LABEL: Record<string, string> = { pending: "승인 대기", active: "사용", locked: "잠김", disabled: "중지" };

/** 가입 승인 · 역할 · 소속 · 잠금 해제 · 비밀번호 초기화 (ADM-02) */
export default function UsersAdmin() {
  const [tab, setTab] = useState<"all" | "pending" | "locked" | "active" | "disabled">("pending");
  const users = useApiData<UserRow[]>("/admin/users");
  const orgs = useApiData<{ orgs: OrgRow[] }>("/admin/orgs");
  const { run, busy } = useAction();
  const list = useMemo(() => (users.data ?? []).filter((u) => tab === "all" || u.status === tab), [users.data, tab]);
  const count = (s: string) => (users.data ?? []).filter((u) => u.status === s).length;
  const orgOptions = (orgs.data?.orgs ?? []).filter((o) => o.active).map((o) => ({ value: o.code, label: `${"　".repeat(o.level - 1)}${o.name}` }));

  const act = (emp: string, action: string, msg: string) => run(() => apiPost(`/admin/users/${emp}/${action}`), msg, users.reload);

  return (
    <AdminPage
      title="사용자"
      description="사번(8자리)으로 가입한 사용자를 승인하고, 소속(부 > 국 > 팀)과 역할을 관리합니다. 화면 권한은 소속 조직 기준으로 상속됩니다. '데이터 책임자' 로 지정하면 자기 부서 사용자가 올린 자료를 [자료 올리기 > 승인할 자료]에서 승인 · 반려합니다."
    >
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "pending", label: "승인 대기", count: count("pending") },
          { key: "active", label: "사용", count: count("active") },
          { key: "locked", label: "잠김", count: count("locked") },
          { key: "disabled", label: "중지", count: count("disabled") },
          { key: "all", label: "전체", count: users.data?.length },
        ]}
      />
      <Card>
        <Loading error={users.error} loading={!users.data && users.loading} />
        <Table head={["사번", "이름 · 직급", "소속", "역할", "데이터 책임자", "상태", "가입 · 최근 로그인", "작업"]}>
          {list.map((u) => (
            <tr key={u.empNo}>
              <C mono>{u.empNo}</C>
              <C>
                <span className="font-bold text-ink-deep">{u.name}</span> {u.position ?? ""}
              </C>
              <C className="min-w-[220px]">
                <Select value={u.org.code} options={orgOptions} onChange={(v) => run(() => apiPatch(`/admin/users/${u.empNo}`, { org_code: v }), "소속을 바꿨습니다", users.reload)} />
                <p className="mt-0.5 text-[10.5px] text-stone">{u.orgPath.map((o) => o.name).join(" > ")}</p>
              </C>
              <C className="w-[110px]">
                <Select value={u.role} options={[{ value: "user", label: "사용자" }, { value: "admin", label: "관리자" }]} onChange={(v) => run(() => apiPatch(`/admin/users/${u.empNo}`, { role: v }), "역할을 바꿨습니다", users.reload)} />
              </C>
              <C className="min-w-[120px]">
                <Check
                  label={u.dataSteward ? "지정" : ""}
                  ariaLabel={`${u.name} 부서 데이터 책임자`}
                  checked={Boolean(u.dataSteward)}
                  onChange={(v) => run(() => apiPatch(`/admin/users/${u.empNo}`, { data_steward: v }), v ? "부서 데이터 책임자로 지정했습니다" : "데이터 책임자 지정을 해제했습니다", users.reload)}
                />
                {u.dataSteward && u.stewardScope ? <p className="mt-0.5 text-[10.5px] text-stone">{u.stewardScope.name} 자료 승인</p> : null}
              </C>
              <C>
                <StatusBadge status={u.status} label={STATUS_LABEL[u.status]} />
                {u.failedCount ? <p className="mt-0.5 text-[10.5px] text-critical">실패 {u.failedCount}회</p> : null}
              </C>
              <C className="text-[11px] text-steel">
                {fmtTime(u.createdAt)}
                <br />
                {fmtTime(u.lastLoginAt)}
              </C>
              <C>
                <div className="flex flex-wrap gap-1">
                  {u.status === "pending" ? (
                    <>
                      <Button size="sm" variant="confirm" disabled={busy} onClick={() => act(u.empNo, "approve", "승인했습니다")}>
                        승인
                      </Button>
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(u.empNo, "reject", "반려했습니다")}>
                        반려
                      </Button>
                    </>
                  ) : null}
                  {u.status === "locked" ? (
                    <Button size="sm" variant="confirm" disabled={busy} onClick={() => act(u.empNo, "unlock", "잠금을 해제했습니다")}>
                      잠금 해제
                    </Button>
                  ) : null}
                  {u.status === "active" ? (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(u.empNo, "disable", "중지했습니다(세션 폐기)")}>
                      중지
                    </Button>
                  ) : null}
                  {u.status === "disabled" ? (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(u.empNo, "enable", "다시 사용하도록 했습니다")}>
                      재사용
                    </Button>
                  ) : null}
                  <Button
                    size="sm"
                    variant="quiet"
                    disabled={busy}
                    onClick={() => {
                      const pw = window.prompt(`${u.name}(${u.empNo}) 새 비밀번호 (8자 이상 · 영문+숫자)`);
                      if (pw) run(() => apiPost(`/admin/users/${u.empNo}/password`, { password: pw }), "비밀번호를 초기화했습니다(기존 세션 폐기)", users.reload);
                    }}
                  >
                    비밀번호
                  </Button>
                </div>
              </C>
            </tr>
          ))}
        </Table>
        {users.data && !list.length ? <p className="py-lg text-center text-[12.5px] text-stone">해당 사용자가 없습니다.</p> : null}
      </Card>
    </AdminPage>
  );
}
