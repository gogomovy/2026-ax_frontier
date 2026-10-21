"use client";

import clsx from "clsx";
import { useEffect, useId, useRef, useState } from "react";
import { useApiData } from "@/components/admin/kit";
import { OrgPicker } from "@/components/admin/OrgPicker";
import { Notice } from "@/components/ui/Layout";
import { Button, PillTabs } from "@/components/ui/primitives";
import { useFocusTrap } from "@/lib/a11y";
import { defaultPick, orgLine, screensLine, switchGroup, type AffGroup, type AffInfo, type AffPick, type AffPickGroup } from "@/lib/affiliation";

export interface ApproveTarget {
  empNo: string;
  name: string;
  passwordRequestAt?: string | null;
}

/**
 * 가입 승인 — 업무 소속을 정하고 승인한다.
 * 인사 조직(.dat)의 팀 · 사무소는 수천 곳이지만 화면은 종합기획부 · 사업부서 · 영업본부 · 영업점 단위에 붙는다.
 * 신청 소속 경로에서 맞는 단위를 먼저 골라 두고(추천), 관리자가 영역 · 단위를 바꾸면 그 소속으로 보게 될 첫 화면 · 업무 화면을 바로 보여 준다.
 * 정한 소속은 인사 동기화가 되돌리지 않는다(서버 hr.orgAssigned).
 */
export function ApproveDialog({ user, busy, onApprove, onClose }: { user: ApproveTarget; busy?: boolean; onApprove: (orgCode: string) => unknown; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [pick, setPick] = useState<AffPick | null>(null);
  const groups = useApiData<{ groups: AffGroup[] }>("/admin/users/affiliations");
  const first = useApiData<AffInfo>(`/admin/users/${encodeURIComponent(user.empNo)}/affiliation`);
  const info = first.data;
  const cur = pick ?? defaultPick(info);
  // 고른 단위의 미리보기 — 처음 값은 첫 응답에 들어 있다
  const previewPath = pick?.code ? `/admin/users/${encodeURIComponent(user.empNo)}/affiliation?org=${encodeURIComponent(pick.code)}` : null;
  const picked = useApiData<AffInfo>(previewPath);
  const preview = pick ? (pick.code ? picked.data?.preview : null) : info?.preview;
  const stale = Boolean(pick?.code && preview?.org.code !== pick.code);
  const gs = groups.data?.groups ?? [];
  const group = gs.find((g) => g.key === cur?.group);
  useFocusTrap(ref, true, { autoFocus: true, restore: true });

  // Esc = 닫기 — 조직 찾기 목록이 열려 있으면 그 목록만 닫히게 둔다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector("[data-org-popover]")) return;
      e.preventDefault();
      onClose();
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const tabs: { key: AffPickGroup; label: string; count?: number }[] = [...gs.map((g) => ({ key: g.key, label: g.label })), { key: "custom" as const, label: "직접 선택" }];
  const choose = (code: string) => setPick({ group: cur?.group ?? "custom", code });
  const loading = !info || !groups.data;
  const error = first.error || groups.error;
  const canApprove = Boolean(cur?.code) && !stale && !busy;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-scrim p-md no-print">
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="max-h-[calc(100vh-32px)] w-full max-w-[600px] animate-pop-in overflow-y-auto rounded-3xl bg-canvas p-xl shadow-popup"
        data-approve-dialog
      >
        <h2 id={titleId} className="text-[17px] font-bold text-ink-deep">
          {user.passwordRequestAt ? "비밀번호 로그인 승인" : "가입 승인"} — 업무 소속 정하기
        </h2>
        <p className="mt-xs text-[13px] leading-relaxed text-charcoal">
          <b className="text-ink-deep">{user.name}</b>({user.empNo})이(가) 볼 화면은 업무 소속으로 정해집니다. 정한 소속은 인사 동기화가 바꾸지 않습니다.
        </p>

        {error ? <p className="mt-md rounded-lg bg-critical-faint px-md py-2.5 text-[12.5px] text-critical">{error}</p> : null}
        {loading && !error ? <p className="mt-md text-[12.5px] text-stone">불러오는 중…</p> : null}

        {info ? (
          <dl className="mt-md grid grid-cols-[88px_1fr] gap-x-sm gap-y-1 rounded-xl bg-surface-soft px-md py-sm text-[12.5px]">
            <dt className="text-steel">신청 소속</dt>
            <dd className="text-charcoal">{orgLine(info.current)}</dd>
            {info.hrOffice && info.hrOffice.code !== info.current?.code ? (
              <>
                <dt className="text-steel">인사 사무소</dt>
                <dd className="text-charcoal">{orgLine(info.hrOffice)}</dd>
              </>
            ) : null}
            <dt className="text-steel">추천</dt>
            <dd className="text-charcoal">{info.suggested ? `${info.suggested.label} — ${orgLine(info.suggested.org)}` : "신청 소속이 어느 영역에도 속하지 않습니다 — 아래에서 정하세요"}</dd>
          </dl>
        ) : null}

        {!loading ? (
          <div className="mt-lg">
            <PillTabs label="업무 소속 영역" size="sm" items={tabs} value={cur?.group ?? "custom"} onChange={(k) => setPick(switchGroup(gs, cur, k))} />
            <div className="mt-md">
              {cur?.group === "custom" ? (
                <OrgPicker label="조직" value={cur.code} valueLabel={info?.current?.code === cur.code ? info.current.name : undefined} placeholder="조직 선택" onChange={(code) => choose(code)} />
              ) : group ? (
                <>
                  {group.options.length ? (
                    <div role="radiogroup" aria-label={`${group.label} 단위`} className="flex max-h-[220px] flex-col gap-1 overflow-y-auto">
                      {group.options.map((o) => (
                        <label
                          key={o.code}
                          className={clsx("flex cursor-pointer items-start gap-sm rounded-lg border px-md py-2", o.code === cur?.code ? "border-primary bg-info-faint" : "border-hairline-soft hover:bg-surface-soft")}
                        >
                          <input type="radio" name={`${titleId}-unit`} className="mt-0.5" checked={o.code === cur?.code} onChange={() => choose(o.code)} />
                          <span className="min-w-0">
                            <span className="block text-[13px] font-bold text-ink-deep">
                              {o.name} <span className="font-mono text-[11px] font-normal text-steel">{o.code}</span>
                            </span>
                            {o.path.length ? <span className="block truncate text-[11px] text-stone">{o.path.join(" > ")}</span> : null}
                          </span>
                        </label>
                      ))}
                    </div>
                  ) : !group.search ? (
                    <Notice tone="attention" title={`${group.label} 단위가 없습니다`}>
                      {group.key === "region" ? "조직에 지역본부 유형이 없습니다. [조직]에서 유형을 확인하세요." : "[화면 설정 › 업무 영역]에서 이 영역의 조직을 정하면 여기에 나옵니다."}
                    </Notice>
                  ) : null}
                  {group.search ? (
                    <div className={group.options.length ? "mt-sm" : ""}>
                      <OrgPicker
                        label={group.options.length ? `다른 ${group.label} 찾기` : `${group.label} 찾기`}
                        value={group.options.some((o) => o.code === cur?.code) ? "" : (cur?.code ?? "")}
                        valueLabel={cur?.code && info?.current?.code === cur.code ? info.current.name : undefined}
                        types={group.search.types}
                        placeholder={`${group.label} 이름 · 코드로 찾기`}
                        onChange={(code) => choose(code)}
                      />
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>

            <section aria-live="polite" aria-busy={stale} className={clsx("mt-md rounded-xl border border-hairline-soft px-md py-sm text-[12.5px]", stale && "opacity-60")}>
              <h3 className="text-[12px] font-bold text-steel">이 소속으로 승인하면</h3>
              {!cur?.code ? (
                <p className="mt-1 text-stone">소속 단위를 고르세요.</p>
              ) : !preview ? (
                <p className="mt-1 text-stone">확인하는 중…</p>
              ) : (
                <>
                  <p className="mt-1 text-charcoal">
                    소속 <b className="text-ink-deep">{orgLine(preview.org)}</b>
                    {preview.affiliation ? ` · ${preview.affiliation.label}` : " · 영역 없음"}
                  </p>
                  {preview.screens.length ? (
                    <p className="mt-0.5 text-charcoal">
                      첫 화면 <b className="text-ink-deep">{preview.home?.label ?? "-"}</b> · 업무 화면 {preview.screens.length}개: {screensLine(preview.screens)}
                    </p>
                  ) : (
                    <div className="mt-xs">
                      <Notice tone="attention" title="볼 수 있는 업무 화면이 없습니다">
                        이 조직(또는 상위 조직)에 화면 권한이 없습니다. 다른 단위를 고르거나 [화면 권한]에서 이 조직에 화면을 주세요.
                      </Notice>
                    </div>
                  )}
                </>
              )}
            </section>
          </div>
        ) : null}

        <div className="mt-lg flex justify-end gap-xs">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 items-center justify-center rounded-md border border-hairline bg-canvas px-4 text-[14px] font-bold text-ink-deep hover:bg-surface-soft"
          >
            취소
          </button>
          <Button variant="primary" disabled={!canApprove} onClick={() => cur?.code && void onApprove(cur.code)} data-approve-ok>
            {preview && !preview.screens.length ? "화면 없이 승인" : "이 소속으로 승인"}
          </Button>
        </div>
      </div>
    </div>
  );
}
