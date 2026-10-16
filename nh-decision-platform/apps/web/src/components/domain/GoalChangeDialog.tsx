"use client";

import { useId, useState } from "react";
import clsx from "clsx";
import { useGoalState, type AddedGoal, type ConsistencyIssue } from "@/components/providers/GoalStateProvider";
import { useUiConfig } from "@/components/providers/SessionProvider";
import { useUi } from "@/components/providers/UiProvider";
import { Sheet } from "@/components/ui/Sheet";
import { Badge, Button } from "@/components/ui/primitives";
import { UNIT_LABEL } from "@/lib/format";
import { defaultRevertTarget, reasonError, valueError } from "@/lib/goalChange";
import { resolveGoal } from "@/lib/goalView";
import type { Goal } from "@/lib/types";
import { threshold } from "@/lib/uiConfig";

/** 다이얼로그를 여는 요청 — 행 메뉴 · 처리 완료 옆 [되돌리기] · 변경 이력 [이 버전으로 복원] 이 모두 이 한 형식을 쓴다 */
export type GoalChangeRequest =
  | { mode: "revert"; goalId: string; toVersion?: number; value?: number | null }
  | { mode: "edit"; goalId: string }
  | { mode: "delete"; goalId: string };

const TITLE = { revert: "목표 되돌리기", edit: "목표 수정", delete: "목표 삭제" } as const;
const SUBMIT = { revert: "되돌리기", edit: "수정 확정", delete: "삭제" } as const;

/**
 * 확정한 경영목표 되돌리기 · 다시 수정 · 삭제 공용 확인 다이얼로그 (결정 = 팝업).
 * 사유는 필수이고, 처리 결과는 지우지 않고 새 버전으로 변경 이력에 남는다.
 */
export function GoalChangeDialog({ request, goal, added, onClose }: { request: GoalChangeRequest; goal?: Goal; added?: AddedGoal; onClose: () => void }) {
  const { overrides, revertGoal, editConfirmedGoal, deleteGoal } = useGoalState();
  const { showToast } = useUi();
  const minReason = Math.max(1, threshold(useUiConfig(), "proposalReasonMin") ?? 1);
  const reasonId = useId();
  const helpId = useId();
  const valueId = useId();
  const errorId = useId();

  const override = goal ? overrides[goal.id] : undefined;
  const view = goal ? resolveGoal(goal, override) : null;
  const unit = goal ? UNIT_LABEL[goal.unit] : "";
  const dec = goal?.decimals ?? 1;
  const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "-" : `${v.toFixed(dec)}${unit}`);
  const target =
    request.mode === "revert" && goal
      ? request.toVersion !== undefined
        ? { version: request.toVersion, value: request.value ?? null }
        : defaultRevertTarget(goal, override)
      : null;

  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const [value, setValue] = useState(view && override?.targetValue !== undefined ? String(override.targetValue) : goal?.targetValue != null ? String(goal.targetValue) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issues, setIssues] = useState<ConsistencyIssue[]>([]);
  const [needsForce, setNeedsForce] = useState(false);

  const rErr = reasonError(reason, minReason);
  const vErr = request.mode === "edit" ? valueError(value) : null;
  const valid = !rErr && !vErr;
  const count = reason.trim().length;
  const title = goal ? (view?.title ?? goal.title) : (added?.title ?? "");

  const submit = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    const r = reason.trim();
    const res =
      request.mode === "revert"
        ? await revertGoal(request.goalId, r, request.toVersion)
        : request.mode === "edit"
          ? await editConfirmedGoal(request.goalId, Number(value), r, needsForce)
          : await deleteGoal(request.goalId, r);
    setBusy(false);
    if (res.ok) {
      const word = request.mode === "revert" ? "되돌렸어요" : request.mode === "edit" ? "수정했어요" : "삭제했어요";
      showToast(res.version !== undefined ? `${word} · v${res.version}으로 기록했어요` : `${word} · 변경 이력에 남겼어요`);
      onClose();
      return;
    }
    setError(res.message);
    setIssues(res.issues ?? []);
    setNeedsForce(Boolean(res.needsForce));
  };

  const submitLabel = busy ? "처리하는 중…" : needsForce && request.mode === "edit" ? "경고 확인 후 수정 확정" : SUBMIT[request.mode];

  return (
    <Sheet
      open
      variant="popup"
      onClose={onClose}
      eyebrow={<span className="text-[12px] font-normal text-steel">경영목표 · 사유 필수</span>}
      title={TITLE[request.mode]}
      meta={title}
      footer={
        <div className="flex w-full justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            취소
          </Button>
          <Button variant={request.mode === "delete" ? "danger" : "primary"} disabled={!valid || busy} onClick={() => void submit()} aria-describedby={!valid ? helpId : undefined}>
            {submitLabel}
          </Button>
        </div>
      }
    >
      <form
        className="flex flex-col gap-4 pb-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {/* 현재 → 바뀔 값 */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-lg bg-info-faint px-5 py-4">
          <div>
            <p className="text-[12px] text-steel">현재 목표{view ? ` · v${view.version}` : ""}</p>
            <p className="tnum mt-0.5 text-[16px] font-bold text-ink-deep">{view ? view.targetLabel : (added?.targetLabel ?? "-")}</p>
          </div>
          {request.mode !== "delete" ? (
            <>
              <span aria-hidden="true" className="text-[18px] text-icon">
                →
              </span>
              {request.mode === "revert" ? (
                <div>
                  <p className="text-[12px] text-steel">되돌릴 값{target ? ` · v${target.version}` : ""}</p>
                  <p className="tnum mt-0.5 text-[20px] font-bold leading-[1.2] text-primary-deep">{fmt(target?.value)}</p>
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  <label htmlFor={valueId} className="text-[12px] text-steel">
                    새 목표값
                  </label>
                  <span className="flex items-center gap-2">
                    <input
                      id={valueId}
                      type="number"
                      step="0.1"
                      inputMode="decimal"
                      value={value}
                      onChange={(e) => {
                        setValue(e.target.value);
                        setNeedsForce(false);
                        setIssues([]);
                      }}
                      aria-invalid={Boolean(vErr)}
                      className="input !w-[130px] font-bold tnum"
                    />
                    <span className="text-[14px] text-steel">{unit}</span>
                  </span>
                  {vErr && value !== "" ? <span className="text-[12px] text-critical">{vErr}</span> : null}
                </div>
              )}
            </>
          ) : null}
        </div>

        {request.mode === "delete" ? <p className="text-[13px] leading-normal text-charcoal">삭제해도 변경 이력은 남아요. 변경 이력의 [이 버전으로 복원]으로 다시 살릴 수 있어요.</p> : null}
        {request.mode === "revert" ? <p className="text-[13px] leading-normal text-charcoal">이전 버전의 값을 새 버전으로 다시 기록해요. 지금까지의 변경 이력은 그대로 남아요.</p> : null}

        <div className="flex flex-col gap-1.5">
          <label htmlFor={reasonId} className="flex items-baseline justify-between gap-2 text-[12px] font-bold text-ink-deep">
            <span>
              사유<span className="ml-0.5 text-critical">*</span>
            </span>
            <span className={clsx("tnum font-normal", count >= minReason ? "text-steel" : "text-attention")} aria-live="polite">
              {count}자 / {minReason}자 이상
            </span>
          </label>
          <textarea
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => setTouched(true)}
            rows={3}
            required
            aria-required="true"
            aria-invalid={touched && Boolean(rErr)}
            aria-describedby={helpId}
            className="input"
            placeholder="예) 지주 협의 결과에 따라 이전 목표로 복귀"
          />
          <p id={helpId} className={clsx("text-[12px]", touched && rErr ? "text-critical" : "text-steel")}>
            {touched && rErr ? rErr : `${minReason}자 이상 적어 주세요 · 처리자와 함께 변경 이력에 남아요`}
          </p>
        </div>

        {issues.length ? (
          <ul className="flex flex-col gap-1.5" data-consistency>
            {issues.map((i) => (
              <li key={i.code} className="flex items-start gap-2 text-[13px]">
                <Badge tone={i.severity === "block" ? "critical" : i.severity === "warn" ? "attention" : "neutral"}>{i.severity === "block" ? "확정 불가" : i.severity === "warn" ? "경고" : "참고"}</Badge>
                <span className="text-charcoal">{i.message}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {error ? (
          <p id={errorId} role="alert" className="rounded-lg bg-surface-soft px-3 py-2 text-[12.5px] font-medium text-critical">
            {error}
          </p>
        ) : null}
      </form>
    </Sheet>
  );
}
