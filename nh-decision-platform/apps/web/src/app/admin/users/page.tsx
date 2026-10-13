"use client";

import { useMemo, useState } from "react";
import { useIsDataAdmin } from "@/components/admin/DataDelete";
import { AdminPage, C, Card, Check, Loading, Select, StatusBadge, Table, Tabs, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { useConfirm } from "@/components/providers/UiProvider";
import { Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";
import { passwordRuleError } from "@/lib/password";

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
  /** 데이터 관리자 — 업로드 자료 삭제 권한 (Phase J · DEL-01 · Q143) */
  dataAdmin?: boolean;
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

  const confirm = useConfirm();
  const act = (emp: string, action: string, msg: string) => run(() => apiPost(`/admin/users/${emp}/${action}`), msg, users.reload);
  const orgName = (code: string) => orgs.data?.orgs.find((o) => o.code === code)?.name ?? code;

  // 되돌리기 어렵거나 권한이 바뀌는 작업은 결과를 설명하고 한 번 더 묻는다 (Phase E · INT-01 · Q123). 취소하면 선택 상자는 원래 값 그대로
  const changeOrg = async (u: UserRow, code: string) => {
    if (code === u.org.code) return;
    const ok = await confirm({ title: "소속을 바꿀까요?", body: `${u.name}(${u.empNo}) — ${u.org.name} → ${orgName(code)}. 화면 권한이 새 소속 기준으로 바로 바뀝니다.`, confirmLabel: "소속 바꾸기" });
    if (ok) await run(() => apiPatch(`/admin/users/${u.empNo}`, { org_code: code }), "소속을 바꿨습니다", users.reload);
  };
  const changeRole = async (u: UserRow, role: string) => {
    if (role === u.role) return;
    const toAdmin = role === "admin";
    const ok = await confirm(
      toAdmin
        ? { title: "관리자 권한을 줄까요?", body: `${u.name}(${u.empNo})은(는) 사용자 · 화면 권한 · 데이터 확정 · LLM 연동 등 모든 관리자 화면을 쓸 수 있게 됩니다.`, confirmLabel: "관리자로 지정", tone: "danger" }
        : { title: "관리자 권한을 회수할까요?", body: `${u.name}(${u.empNo})은(는) 소속 조직의 업무 화면만 쓰게 됩니다.`, confirmLabel: "권한 회수" },
    );
    if (ok) await run(() => apiPatch(`/admin/users/${u.empNo}`, { role }), "역할을 바꿨습니다", users.reload);
  };
  // 데이터 관리자 (Phase J · Q143) — 업로드 자료 삭제 권한. 데이터 관리자만 바꿀 수 있다(서버가 최종 판정)
  const iAmDataAdmin = useIsDataAdmin();
  const changeDataAdmin = async (u: UserRow, v: boolean) => {
    const ok = await confirm(
      v
        ? { title: "데이터 관리자로 지정할까요?", body: `${u.name}(${u.empNo})은(는) 업로드된 데이터셋 버전 · 문서를 삭제할 수 있게 됩니다. 삭제는 되돌릴 수 없습니다.`, confirmLabel: "지정", tone: "danger" }
        : { title: "데이터 관리자 지정을 해제할까요?", body: `${u.name}(${u.empNo})은(는) 업로드 자료를 삭제할 수 없게 됩니다.`, confirmLabel: "해제" },
    );
    if (ok) await run(() => apiPatch(`/admin/users/${u.empNo}`, { data_admin: v }), v ? "데이터 관리자로 지정했습니다" : "데이터 관리자 지정을 해제했습니다", users.reload);
  };
  const disable = async (u: UserRow) => {
    const ok = await confirm({ title: "사용을 중지할까요?", body: `${u.name}(${u.empNo})의 로그인 세션이 바로 끊기고 다시 로그인할 수 없습니다. [재사용]으로 되돌릴 수 있습니다.`, confirmLabel: "중지", tone: "danger" });
    if (ok) await act(u.empNo, "disable", "중지했습니다(세션 폐기)");
  };
  const reject = async (u: UserRow) => {
    const ok = await confirm({ title: "가입 신청을 반려할까요?", body: `${u.name}(${u.empNo})의 가입 신청을 반려합니다. 다시 쓰려면 새로 가입해야 합니다.`, confirmLabel: "반려", tone: "danger" });
    if (ok) await act(u.empNo, "reject", "반려했습니다");
  };
  const resetPassword = async (u: UserRow) => {
    const pw = await confirm({
      title: "비밀번호를 초기화할까요?",
      body: `${u.name}(${u.empNo})의 기존 로그인 세션이 모두 끊깁니다. 새 비밀번호는 본인에게 안전한 경로로 알려 주세요.`,
      confirmLabel: "초기화",
      input: { label: "새 비밀번호 (8자 이상 · 영문 + 숫자)", type: "password", validate: passwordRuleError },
    });
    if (typeof pw === "string" && pw) await run(() => apiPost(`/admin/users/${u.empNo}/password`, { password: pw }), "비밀번호를 초기화했습니다(기존 세션 폐기)", users.reload);
  };

  return (
    <AdminPage
      title="사용자"
      description="사번(8자리)으로 가입한 사용자를 승인하고, 소속(부 > 국 > 팀)과 역할을 관리합니다. 화면 권한은 소속 조직 기준으로 상속됩니다. '데이터 책임자' 로 지정하면 자기 부서 사용자가 올린 자료를 [자료 올리기 > 승인할 자료]에서 승인 · 반려합니다. '데이터 관리자'(관리자 중 지정)만 업로드된 데이터셋 버전 · 문서를 삭제할 수 있고, 지정 · 해제도 데이터 관리자만 합니다."
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
        <Table head={["사번", "이름 · 직급", "소속", "역할", "데이터 책임자", "데이터 관리자", "상태", "가입 · 최근 로그인", "작업"]}>
          {list.map((u) => (
            <tr key={u.empNo}>
              <C mono>{u.empNo}</C>
              <C>
                <span className="font-bold text-ink-deep">{u.name}</span> {u.position ?? ""}
              </C>
              <C className="min-w-[220px]">
                <Select ariaLabel={`${u.name} 소속`} value={u.org.code} options={orgOptions} onChange={(v) => void changeOrg(u, v)} />
                <p className="mt-0.5 text-[10.5px] text-stone">{u.orgPath.map((o) => o.name).join(" > ")}</p>
              </C>
              <C className="w-[110px]">
                <Select ariaLabel={`${u.name} 역할`} value={u.role} options={[{ value: "user", label: "사용자" }, { value: "admin", label: "관리자" }]} onChange={(v) => void changeRole(u, v)} />
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
              <C className="min-w-[120px]">
                {u.role === "admin" ? (
                  <>
                    <Check
                      label={u.dataAdmin ? "지정" : ""}
                      ariaLabel={`${u.name} 데이터 관리자`}
                      checked={Boolean(u.dataAdmin)}
                      disabled={!iAmDataAdmin || busy}
                      onChange={(v) => void changeDataAdmin(u, v)}
                    />
                    {u.dataAdmin ? <p className="mt-0.5 text-[10.5px] text-stone">업로드 자료 삭제</p> : null}
                  </>
                ) : (
                  <span className="text-[11px] text-stone">관리자만</span>
                )}
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
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => void reject(u)}>
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
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => void disable(u)}>
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
                    onClick={() => void resetPassword(u)}
                    aria-label={`${u.name} 비밀번호 초기화`}
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
