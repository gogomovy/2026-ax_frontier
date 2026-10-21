"use client";

import { useEffect, useState } from "react";
import { ApproveDialog } from "@/components/admin/ApproveDialog";
import { useIsDataAdmin } from "@/components/admin/DataDelete";
import { AdminPage, C, Card, Check, Loading, Select, StatusBadge, Table, Tabs, TextInput, fmtTime, useAction, useApiData } from "@/components/admin/kit";
import { OrgPicker } from "@/components/admin/OrgPicker";
import { useConfirm } from "@/components/providers/UiProvider";
import { Badge, Button } from "@/components/ui/primitives";
import { apiPatch, apiPost } from "@/lib/api-client";
import { passwordRuleError } from "@/lib/password";
import { pageRange, usersPath, type UserTab } from "@/lib/usersQuery";

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
  /** 계정 출처 (Phase R) — local(가입) · dat(인사 동기화 · SSO 전용) · sso(SSO 자동 생성) */
  source?: "local" | "dat" | "sso";
  /** 인사 동기화 사번이 가입 화면에서 낸 사번 · 비밀번호 로그인 신청 시각 (Phase R) — 승인 전까지 비밀번호 로그인 불가, SSO 는 그대로 */
  passwordRequestAt?: string | null;
  /** 관리자가 정한 업무 소속 — 인사 동기화가 사무소 기준으로 되돌리지 않는다 */
  orgAssigned?: { code: string; by: string; at: string; from?: string } | null;
  /** 인사(.dat) 사무소 */
  hrOffice?: { code: string; name: string | null } | null;
}

/** 승인 대기 = 가입 승인 대기 + 인사 동기화 사번의 비밀번호 로그인 신청 */
const isPending = (u: UserRow) => u.status === "pending" || Boolean(u.passwordRequestAt);

/** 서버가 걸러 한 쪽씩 돌려준다 — 인사 동기화로 수천 명이어도 화면이 멈추지 않게 (counts = 같은 검색 조건의 탭별 건수) */
interface UsersPage {
  items: UserRow[];
  total: number;
  page: number;
  size: number;
  counts: Record<UserTab, number>;
  status: UserTab;
  q: string;
  org: string | null;
}

const STATUS_LABEL: Record<string, string> = { pending: "승인 대기", active: "사용", locked: "잠김", disabled: "중지" };
const EMPTY_TEXT: Record<UserTab, string> = { pending: "승인을 기다리는 사용자가 없습니다.", active: "사용 중인 사용자가 없습니다.", locked: "잠긴 사용자가 없습니다.", disabled: "중지된 사용자가 없습니다.", all: "사용자가 없습니다." };
const PAGE_SIZE = 50;

/** 가입 승인 · 역할 · 소속 · 잠금 해제 · 비밀번호 초기화 (ADM-02) */
export default function UsersAdmin() {
  const [tab, setTab] = useState<UserTab>("pending");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [org, setOrg] = useState<{ code: string; name: string } | null>(null);
  const [page, setPage] = useState(1);
  // 검색어는 입력이 멈추고 0.3초 뒤에 반영(그때 첫 쪽으로)
  useEffect(() => {
    const t = window.setTimeout(() => {
      const next = text.trim().slice(0, 50); // 서버도 50자까지만 본다(응답의 q 와 맞춰 '흐리게' 판정)
      if (next === query) return;
      setQuery(next);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [text, query]);
  const users = useApiData<UsersPage>(usersPath({ status: tab, q: query, org: org?.code, page, size: PAGE_SIZE }));
  const d = users.data;
  // 탭 · 검색을 바꾼 직후 — 새 결과가 올 때까지 이전 목록을 흐리게
  const stale = Boolean(d && (d.status !== tab || d.q !== query || (d.org ?? null) !== (org?.code ?? null)));
  const list = d?.items ?? [];
  const range = d ? pageRange(d.page, d.size, d.total) : null;
  const { run, busy } = useAction();

  const confirm = useConfirm();
  const act = (emp: string, action: string, msg: string) => run(() => apiPost(`/admin/users/${emp}/${action}`), msg, users.reload);
  // 승인 — 업무 소속(종합기획부 · 사업부서 · 영업본부 · 영업점)을 정하는 대화상자에서
  const [approving, setApproving] = useState<UserRow | null>(null);
  const approve = async (u: UserRow, orgCode: string) => {
    const r = await run(() => apiPost(`/admin/users/${u.empNo}/approve`, { org_code: orgCode }), u.passwordRequestAt ? "비밀번호 로그인을 승인했습니다" : "승인했습니다", users.reload);
    if (r !== null) setApproving(null);
  };
  const followHr = async (u: UserRow) => {
    const ok = await confirm({
      title: "인사 기준 소속으로 되돌릴까요?",
      body: `${u.name}(${u.empNo}) — 관리자가 정한 소속(${u.org.name})을 풀고 인사 사무소${u.hrOffice?.name ? `(${u.hrOffice.name})` : ""}로 옮깁니다. 이후에는 인사 동기화가 소속을 맞춥니다. 화면 권한이 바로 바뀝니다.`,
      confirmLabel: "인사 기준으로",
    });
    if (ok) await run(() => apiPatch(`/admin/users/${u.empNo}`, { follow_hr: true }), "인사 기준 소속으로 되돌렸습니다", users.reload);
  };

  // 되돌리기 어렵거나 권한이 바뀌는 작업은 결과를 설명하고 한 번 더 묻는다 (Phase E · INT-01 · Q123). 취소하면 선택 상자는 원래 값 그대로
  const changeOrg = async (u: UserRow, code: string, name?: string) => {
    if (!code || code === u.org.code) return;
    const ok = await confirm({ title: "소속을 바꿀까요?", body: `${u.name}(${u.empNo}) — ${u.org.name} → ${name ?? code}. 화면 권한이 새 소속 기준으로 바로 바뀝니다.`, confirmLabel: "소속 바꾸기" });
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
    const ok = await confirm(
      u.passwordRequestAt
        ? { title: "비밀번호 로그인 신청을 반려할까요?", body: `${u.name}(${u.empNo})이(가) 정한 비밀번호를 지웁니다. 계정은 그대로라 사내 SSO 로그인은 계속 됩니다.`, confirmLabel: "반려", tone: "danger" }
        : { title: "가입 신청을 반려할까요?", body: `${u.name}(${u.empNo})의 가입 신청을 반려합니다. 다시 쓰려면 새로 가입해야 합니다.`, confirmLabel: "반려", tone: "danger" },
    );
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
        onChange={(k) => {
          setTab(k);
          setPage(1);
        }}
        tabs={[
          { key: "pending", label: "승인 대기", count: d?.counts.pending },
          { key: "active", label: "사용", count: d?.counts.active },
          { key: "locked", label: "잠김", count: d?.counts.locked },
          { key: "disabled", label: "중지", count: d?.counts.disabled },
          { key: "all", label: "전체", count: d?.counts.all },
        ]}
      />
      <Card>
        <div className="mb-md flex flex-wrap items-end gap-md" role="search" aria-label="사용자 찾기">
          <TextInput label="찾기" value={text} onChange={setText} placeholder="사번 · 이름 · 소속 조직 이름" className="w-[280px]" />
          <OrgPicker
            label="소속(하위 조직 포함)"
            value={org?.code ?? ""}
            valueLabel={org?.name}
            empty="전체 조직"
            includeInactive
            className="w-[260px]"
            onChange={(code, o) => {
              setOrg(code ? { code, name: o?.name ?? code } : null);
              setPage(1);
            }}
          />
          {query || org ? (
            <Button
              size="sm"
              variant="quiet"
              onClick={() => {
                setText("");
                setQuery("");
                setOrg(null);
                setPage(1);
              }}
            >
              조건 지우기
            </Button>
          ) : null}
          {d && range ? (
            <p className="ml-auto text-[12px] text-steel tnum" role="status" aria-live="polite">
              {d.total ? `${range.from.toLocaleString("ko-KR")}–${range.to.toLocaleString("ko-KR")} / ${d.total.toLocaleString("ko-KR")}명` : "0명"}
            </p>
          ) : null}
        </div>
        <Loading error={users.error} loading={!d && users.loading} />
        <div className={stale ? "opacity-60 transition-opacity" : "transition-opacity"} aria-busy={stale}>
        <Table head={["사번", "이름 · 직급", "소속", "역할", "데이터 책임자", "데이터 관리자", "상태", "가입 · 최근 로그인", "작업"]}>
          {list.map((u) => (
            <tr key={u.empNo}>
              <C mono>{u.empNo}</C>
              <C>
                <span className="font-bold text-ink-deep">{u.name}</span> {u.position ?? ""}
                {u.source === "dat" || u.source === "sso" ? (
                  <Badge tone="info" className="ml-1">
                    {u.source === "dat" ? "인사 동기화" : "SSO 생성"}
                  </Badge>
                ) : null}
              </C>
              <C className="min-w-[220px]">
                <OrgPicker ariaLabel={`${u.name} 소속`} value={u.org.code} valueLabel={u.org.name} disabled={busy} onChange={(code, o) => void changeOrg(u, code, o?.name)} />
                <p className="mt-0.5 text-[10.5px] text-stone">{u.orgPath.map((o) => o.name).join(" > ")}</p>
                {u.orgAssigned ? (
                  <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[10.5px] text-steel">
                    <span title={`${u.orgAssigned.by} · ${fmtTime(u.orgAssigned.at)} — 인사 동기화가 이 소속을 바꾸지 않습니다`}>
                      <Badge tone="info">관리자 지정</Badge>
                    </span>
                    {u.hrOffice && u.hrOffice.code !== u.org.code ? <span>인사 사무소 {u.hrOffice.name ?? u.hrOffice.code}</span> : null}
                    {u.source === "dat" && u.hrOffice ? (
                      <button type="button" className="font-bold text-primary disabled:opacity-50" disabled={busy} onClick={() => void followHr(u)}>
                        인사 기준으로
                      </button>
                    ) : null}
                  </p>
                ) : null}
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
                {u.dataSteward && u.stewardScope ? <p className="mt-0.5 text-[10.5px] text-stone">{u.stewardScope.name} 자료 승인 · 삭제</p> : null}
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
                {u.passwordRequestAt ? (
                  <p className="mt-0.5" title={`신청 ${fmtTime(u.passwordRequestAt)}`}>
                    <Badge tone="attention">비밀번호 로그인 신청</Badge>
                  </p>
                ) : null}
                {u.failedCount ? <p className="mt-0.5 text-[10.5px] text-critical">실패 {u.failedCount}회</p> : null}
              </C>
              <C className="text-[11px] text-steel">
                {fmtTime(u.createdAt)}
                <br />
                {fmtTime(u.lastLoginAt)}
              </C>
              <C>
                <div className="flex flex-wrap gap-1">
                  {isPending(u) ? (
                    <>
                      <Button size="sm" variant="confirm" disabled={busy} onClick={() => setApproving(u)} aria-label={`${u.name} 승인 — 업무 소속 정하기`}>
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
        </div>
        {d && !stale && !list.length ? (
          <p className="py-lg text-center text-[12.5px] text-stone">{query || org ? "검색 조건에 맞는 사용자가 없습니다." : EMPTY_TEXT[tab]}</p>
        ) : null}
        {d && range && range.pages > 1 ? (
          <nav aria-label="사용자 목록 쪽" className="mt-md flex items-center justify-center gap-sm text-[12px] text-steel">
            <Button size="sm" variant="ghost" disabled={d.page <= 1 || stale} onClick={() => setPage(d.page - 1)}>
              이전
            </Button>
            <span className="tnum" aria-current="page">
              {d.page.toLocaleString("ko-KR")} / {range.pages.toLocaleString("ko-KR")}쪽
            </span>
            <Button size="sm" variant="ghost" disabled={d.page >= range.pages || stale} onClick={() => setPage(d.page + 1)}>
              다음
            </Button>
          </nav>
        ) : null}
      </Card>
      {approving ? <ApproveDialog user={approving} busy={busy} onApprove={(code) => approve(approving, code)} onClose={() => setApproving(null)} /> : null}
    </AdminPage>
  );
}
