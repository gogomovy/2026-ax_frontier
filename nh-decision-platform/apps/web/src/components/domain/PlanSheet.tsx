"use client";

import { useState } from "react";
import { EvidenceSummary } from "@/components/evidence/EvidenceChips";
import { FormField } from "@/components/domain/GoalSheets";
import { AlignmentPanel } from "@/components/domain/Verification";
import { usePlanState } from "@/components/providers/PlanStateProvider";
import { useUi } from "@/components/providers/UiProvider";
import { LinkedAnalysisSection } from "@/components/domain/LinkedAnalysis";
import { Sheet, SheetSection } from "@/components/ui/Sheet";
import { Badge, Button, IconCheck, Switch } from "@/components/ui/primitives";
import { formatDate } from "@/lib/format";
import type { ActionPlan, AnalysisTab } from "@/lib/types";

const CYCLES = ["월", "분기", "반기", "연"];

/**
 * 수행방안 상세 시트 (요구사항 CRM-08 ~ CRM-13)
 *  view   — 근거·지표·배치 검증·연결 분석 + 등록/해제·영업점 참고·수정·삭제
 *  edit   — 제목·내용·지표·주기·연결 분석(직접 등록 건은 근거 메모 포함) 수정
 *  create — 사업·분석 직접 추가
 *  readOnly 이면 종합기획부 조회용으로 상태 변경 액션을 감춘다.
 */
export function PlanSheet({
  plan,
  tabs,
  mode: initialMode = "view",
  readOnly,
  onClose,
}: {
  plan?: ActionPlan;
  tabs: AnalysisTab[];
  mode?: "view" | "edit" | "create";
  readOnly?: boolean;
  onClose: () => void;
}) {
  const [mode, setMode] = useState(plan ? initialMode : "create");

  if (mode === "view" && plan) {
    return <PlanView plan={plan} readOnly={readOnly} onClose={onClose} onEdit={() => setMode("edit")} />;
  }
  return (
    <PlanForm
      plan={mode === "edit" ? plan : undefined}
      tabs={tabs}
      onClose={onClose}
      onDone={() => (plan ? setMode("view") : onClose())}
    />
  );
}

function PlanView({
  plan,
  readOnly,
  onClose,
  onEdit,
}: {
  plan: ActionPlan;
  readOnly?: boolean;
  onClose: () => void;
  onEdit: () => void;
}) {
  const { registerPlan, unregisterPlan, toggleBranchShare, deletePlan } = usePlanState();
  const { showToast } = useUi();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const running = plan.status === "in_progress";
  const blocked = plan.alignment.verdict === "conflict";

  const footer = readOnly ? undefined : confirmDelete ? (
    <>
      <span className="text-[12.5px] font-bold text-critical">삭제하면 전파 경로와 종합기획부 화면에서도 사라집니다.</span>
      <Button
        variant="secondary"
        size="sm"
        className="ml-auto"
        onClick={() => {
          deletePlan(plan.id);
          showToast("삭제했습니다");
          onClose();
        }}
      >
        삭제
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
        취소
      </Button>
    </>
  ) : (
    <>
      {running ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            unregisterPlan(plan.id);
            showToast("진행사업 등록을 해제했습니다 — 제안안으로 돌아갑니다");
          }}
        >
          등록 해제
        </Button>
      ) : (
        <Button
          variant="confirm"
          size="sm"
          disabled={blocked}
          title={blocked ? "상위 기준과 배치되어 등록할 수 없습니다" : undefined}
          onClick={() => {
            registerPlan(plan.id);
            showToast("진행사업으로 등록했습니다 — 종합기획부에서 조회됩니다");
          }}
        >
          <IconCheck />
          진행사업 등록
        </Button>
      )}
      <Button variant="ghost" size="sm" onClick={onEdit}>
        수정
      </Button>
      <button
        type="button"
        onClick={() => setConfirmDelete(true)}
        className="ml-auto text-[12.5px] font-bold text-critical"
      >
        삭제
      </button>
    </>
  );

  return (
    <Sheet
      open
      onClose={onClose}
      width="lg"
      eyebrow={
        <>
          <Badge tone={running ? "success" : "neutral"}>{running ? "진행중인 사업" : "제안안"}</Badge>
          <Badge tone={plan.origin === "user" ? "info" : "dark"}>{plan.origin === "user" ? "직접 등록" : "AI 제안"}</Badge>
          <AlignmentPanel compact verdict={plan.alignment.verdict} matched={[]} conflicts={[]} />
        </>
      }
      title={plan.title}
      meta={[
        plan.ownerOrg,
        `점검 주기 ${plan.reviewCycle}`,
        plan.registeredAt ? `등록 ${formatDate(plan.registeredAt)}` : null,
        plan.updatedAt ? `수정 ${formatDate(plan.updatedAt)}` : null,
      ]
        .filter(Boolean)
        .join(" · ")}
      footer={footer}
    >
      {running && !readOnly ? (
        <div className="mb-lg flex items-center justify-between gap-base rounded-xl border border-hairline-soft px-base py-3">
          <Switch
            checked={plan.branchShared}
            onChange={() => toggleBranchShare(plan.id)}
            label={plan.branchShared ? "영업점 AI 참고 가능" : "영업점 AI 참고 중단"}
            description="켜면 영업점 화면 · 질문하기 · 영업점 AI가 이 수행방안과 연결 분석(요약)을 함께 참고하고, 전파 경로에 영업점이 연결됩니다. 언제든 다시 바꿀 수 있습니다."
          />
        </div>
      ) : null}
      {running && readOnly ? (
        <p className="mb-lg rounded-xl bg-surface-soft px-base py-3 text-[12.5px] text-charcoal">
          영업점 AI 참고 <b>{plan.branchShared ? "가능" : "중단"}</b> 상태입니다.
        </p>
      ) : null}

      <SheetSection title="내용">
        <p className="text-[14px] leading-[1.7] text-charcoal">{plan.body}</p>
      </SheetSection>
      {plan.guide ? (
        <SheetSection title="가이드(규칙 판정)">
          <div className="rounded-lg bg-surface-soft px-3 py-2.5" data-plan-guide={plan.guide.ruleId}>
            <p className="text-[13px] font-bold text-ink-deep">{plan.guide.title ?? plan.guide.ruleId}</p>
            {plan.guide.text ? <p className="mt-1 text-[12.5px] leading-relaxed text-charcoal">{plan.guide.text}</p> : null}
            <ul className="mt-1.5 flex flex-col gap-0.5">
              {plan.guide.basis.map((b, i) => (
                <li key={i} className="text-[11.5px] text-steel tnum">
                  {b.label ?? b.metric} {b.value ?? "-"} {b.op} {b.threshold} {b.met ? "· 충족" : "· 미충족"}
                </li>
              ))}
            </ul>
            <p className="mt-1 text-[10.5px] text-stone">조건 · 문구는 관리자 [판정 규칙] GUIDE_CATALOG 에서 관리합니다.</p>
          </div>
        </SheetSection>
      ) : null}

      <SheetSection title="모니터링 지표">
        {plan.monitoringMetrics.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {plan.monitoringMetrics.map((m) => (
              <span key={m} className="rounded-pill bg-surface-soft px-3 py-1 text-[12px] font-medium text-charcoal">
                {m}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-[12.5px] text-stone">지정된 지표가 없습니다.</p>
        )}
        <p className="mt-2.5 text-[12px] text-steel">관련 경영목표 · {plan.relatedGoalTitle ?? "연결된 목표 없음"}</p>
      </SheetSection>

      <SheetSection title="근거">
        <EvidenceSummary items={plan.evidence} title={plan.title} />
        {plan.evidenceNote ? (
          <p className="mt-2.5 rounded-lg bg-surface-soft px-3 py-2 text-[12.5px] leading-relaxed text-charcoal">
            담당자 메모 · {plan.evidenceNote}
          </p>
        ) : null}
      </SheetSection>

      <SheetSection title="배치 검증">
        <AlignmentPanel
          verdict={plan.alignment.verdict}
          matched={plan.alignment.matched}
          conflicts={plan.alignment.conflicts}
        />
      </SheetSection>

      <SheetSection title="연결 분석">
        {/* 보고서 주소는 서버가 분석 공간에서 정한다(부서 화면 경로를 화면에 두지 않음). 열 수 없는 사용자(영업점)는 요약을 본다 */}
        <LinkedAnalysisSection plan={plan} />
      </SheetSection>
    </Sheet>
  );
}

function PlanForm({
  plan,
  tabs,
  onClose,
  onDone,
}: {
  plan?: ActionPlan;
  tabs: AnalysisTab[];
  onClose: () => void;
  onDone: () => void;
}) {
  const { addPlan, updatePlan } = usePlanState();
  const { showToast } = useUi();
  const isUserPlan = !plan || plan.origin === "user";
  const [title, setTitle] = useState(plan?.title ?? "");
  const [body, setBody] = useState(plan?.body ?? "");
  const [note, setNote] = useState(plan?.evidenceNote ?? "");
  const [metrics, setMetrics] = useState(plan?.monitoringMetrics.join(", ") ?? "");
  const [cycle, setCycle] = useState(plan?.reviewCycle ?? "월");
  const [tabKey, setTabKey] = useState(plan?.linkedTabKey ?? "");

  const parsedMetrics = metrics
    .split(",")
    .map((m) => m.trim())
    .filter(Boolean);
  const linked = tabs.find((t) => t.tabKey === tabKey);

  const save = () => {
    if (plan) {
      updatePlan(plan.id, {
        title: title.trim(),
        body: body.trim(),
        monitoringMetrics: parsedMetrics,
        reviewCycle: cycle,
        linkedTabKey: linked?.tabKey,
        linkedAnalysisLabel: linked?.label,
        ...(isUserPlan ? { evidenceNote: note.trim() } : {}),
      });
      showToast("수정했습니다");
    } else {
      addPlan({
        title: title.trim(),
        body: body.trim(),
        evidenceNote: note.trim() || undefined,
        monitoringMetrics: parsedMetrics,
        reviewCycle: cycle,
        linkedTabKey: linked?.tabKey,
        linkedAnalysisLabel: linked?.label,
      });
      showToast("제안안으로 추가했습니다 — 진행사업 등록 시 종합기획부에 공유됩니다");
    }
    onDone();
  };

  return (
    <Sheet
      open
      onClose={onClose}
      width="lg"
      eyebrow={<Badge tone="neutral">{plan ? "수정" : "직접 추가"}</Badge>}
      title={plan ? "수행방안 수정" : "사업·분석 직접 추가"}
      meta={plan ? plan.title : "AI 제안과 같은 구조로 등록되며 제안안으로 시작합니다."}
      footer={
        <>
          <Button variant="confirm" size="sm" disabled={!title.trim() || !body.trim()} onClick={save}>
            {plan ? "저장" : "제안안으로 추가"}
          </Button>
          <Button variant="ghost" size="sm" onClick={plan ? onDone : onClose}>
            취소
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-base">
        <FormField label="제목" required>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예) 기업형소호 부도율 상승 구간 집중 점검"
            className="input"
          />
        </FormField>
        <FormField label="내용" required>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={5}
            placeholder="점검 대상, 수행 방식, 판단 기준을 적습니다."
            className="input"
          />
        </FormField>
        {isUserPlan ? (
          <FormField label="근거">
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="참고한 자료·회의 결정·데이터를 남깁니다. 문서 연결은 백엔드 연동 시 지원됩니다."
              className="input"
            />
          </FormField>
        ) : (
          <p className="rounded-lg bg-surface-soft px-3 py-2.5 text-[12px] leading-relaxed text-steel">
            AI가 수집한 근거는 판단 이력 보존을 위해 수정할 수 없습니다.
          </p>
        )}
        <FormField label="모니터링 지표 (쉼표로 구분)">
          <input
            value={metrics}
            onChange={(e) => setMetrics(e.target.value)}
            placeholder="기업형소호 부도율, 신규 취급 건수"
            className="input"
          />
        </FormField>
        <div className="grid grid-cols-1 gap-base sm:grid-cols-2">
          <FormField label="점검 주기">
            <select value={cycle} onChange={(e) => setCycle(e.target.value)} className="input">
              {CYCLES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </FormField>
          <FormField label="연결 분석">
            <select value={tabKey} onChange={(e) => setTabKey(e.target.value)} className="input">
              <option value="">연결 없음</option>
              {tabs.map((t) => (
                <option key={t.tabKey} value={t.tabKey}>
                  {t.label}
                </option>
              ))}
            </select>
          </FormField>
        </div>
        {!plan ? (
          <p className="text-[11.5px] leading-relaxed text-stone">
            직접 추가한 항목의 배치 검증은 `확인 필요`로 시작합니다. 상위 기준 대조는 백엔드 연동 시 자동으로 수행됩니다.
          </p>
        ) : null}
      </div>
    </Sheet>
  );
}
